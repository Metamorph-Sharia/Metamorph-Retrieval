"""Build one snapshot: chunks, document metadata, vectors, validation, and the swap.

Nothing is live until `activate`. Building writes tables named after the snapshot,
so a failed run leaves the previous snapshot answering (ADR-002).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import psycopg

from .chunks import CHUNK_DDL, COMMON_SHARE, DOCUMENTS, META_DDL, PROVISIONS, STEMS_DDL, Chunk, Provision, chunk
from .config import excluded_documents, index_url, published_url, table_name, tag

BUILD_DDL = """
create table if not exists regulation_build (
  snapshot_id text primary key,
  chunk_table text not null,
  embed_table text not null,
  meta_table text not null,
  chunk_count integer not null,
  searchable_count integer not null,
  vector_count integer not null,
  status text not null,
  source_fingerprint text,
  built_at timestamptz not null default now()
)
"""

SOURCE = """
select (select count(*) from published.document),
       (select count(*) from published.provision where body <> ''),
       (select max(published_at) from published.document)
"""

COPY = (
    "copy {table} (chunk_id, snapshot_id, document_id, text_sha256, source_address, address, "
    "part, part_count, kind, label, heading, title, citation, issuer, doc_status, valid_from, "
    "valid_to, body, body_md5, body_chars, context_text, context_hash, token_count, "
    "searchable, flags) from stdin"
)


@dataclass(frozen=True)
class Tables:
    chunks: str
    embeddings: str
    meta: str

    @property
    def stems(self) -> str:
        """The word search's stems, named after the chunks they were counted in (stems_table)."""
        return stems_table(self.chunks)

    @classmethod
    def for_snapshot(cls, snapshot: str) -> Tables:
        suffix = tag(snapshot)
        return cls(f"regulation_chunk_{suffix}", f"regulation_emb_{suffix}", f"regulation_meta_{suffix}")


def source_fingerprint() -> str:
    """What "the source changed" means: counts and the newest publish."""
    with psycopg.connect(published_url()) as conn:
        documents, provisions, published_at = conn.execute(SOURCE).fetchone()
    return f"{documents}:{provisions}:{published_at.isoformat() if published_at else 'none'}"


def build(snapshot: str, tables: Tables, *, limit: int | None = None) -> int:
    excluded = excluded_documents()
    with psycopg.connect(published_url()) as source:
        rows = source.execute(PROVISIONS, (excluded,)).fetchall()
    provisions = [Provision(*row) for row in rows]
    if limit:
        provisions = provisions[:limit]

    started = time.perf_counter()
    with psycopg.connect(index_url()) as target:
        with target.cursor() as cursor:
            cursor.execute(f"drop table if exists {table_name(tables.chunks)}")
            cursor.execute(CHUNK_DDL.format(table=table_name(tables.chunks)))
            with cursor.copy(COPY.format(table=tables.chunks)) as copy:
                for provision in provisions:
                    copy.write_row(chunk_row(chunk(provision, snapshot), snapshot))
            cursor.execute(
                f"create index {tables.chunks}_document on {tables.chunks} (document_id, address)"
            )
            cursor.execute(f"create index {tables.chunks}_words on {tables.chunks} using gin (words)")
            cursor.execute(f"drop table if exists {table_name(tables.stems)}")
            cursor.execute(STEMS_DDL.format(stems=tables.stems, chunks=tables.chunks, share=COMMON_SHARE))
            cursor.execute(f"alter table {tables.stems} add primary key (word)")
        target.commit()
    print(f"chunks: {len(provisions):,} in {time.perf_counter() - started:.1f}s", flush=True)
    return len(provisions)


def build_metadata(tables: Tables) -> int:
    with psycopg.connect(published_url()) as source:
        rows = source.execute(DOCUMENTS, (excluded_documents(),)).fetchall()
    with psycopg.connect(index_url()) as target:
        with target.cursor() as cursor:
            cursor.execute(f"drop table if exists {table_name(tables.meta)}")
            cursor.execute(META_DDL.format(table=table_name(tables.meta)))
            with cursor.copy(f"copy {tables.meta} from stdin") as copy:
                for row in rows:
                    copy.write_row(row)
        target.commit()
    print(f"documents: {len(rows):,}", flush=True)
    return len(rows)


def validate(tables: Tables, *, require_vectors: bool) -> list[str]:
    with psycopg.connect(index_url()) as conn:
        def scalar(query: str) -> int:
            return conn.execute(query).fetchone()[0]

        chunks = scalar(f"select count(*) from {tables.chunks}")
        orphans = scalar(
            f"select count(*) from {tables.chunks} c left join {tables.meta} m using (document_id) "
            "where m.document_id is null"
        )
        empty = scalar(f"select count(*) from {tables.chunks} where body = '' or address = '' or title = ''")
        searchable = scalar(f"select count(*) from {tables.chunks} where searchable")
        vectors = scalar(f"select count(*) from {tables.embeddings}") if exists(conn, tables.embeddings) else 0

    problems = []
    if chunks == 0:
        problems.append("chunks: the build wrote no rows")
    if orphans:
        problems.append(f"documents: {orphans:,} chunks have no document metadata")
    if empty:
        problems.append(f"chunks: {empty:,} rows have an empty body, address or title")
    if searchable == 0:
        problems.append("searchable: no chunk is searchable")
    if require_vectors and vectors != searchable:
        problems.append(f"vectors: {vectors:,} for {searchable:,} searchable chunks")
    return problems


def record(snapshot: str, tables: Tables, status: str) -> None:
    with psycopg.connect(index_url()) as conn:
        conn.execute(BUILD_DDL)
        conn.execute("alter table regulation_build add column if not exists source_fingerprint text")
        chunks, searchable = conn.execute(
            f"select count(*), count(*) filter (where searchable) from {tables.chunks}"
        ).fetchone()
        vectors = conn.execute(f"select count(*) from {tables.embeddings}").fetchone()[0] if exists(
            conn, tables.embeddings
        ) else 0
        conn.execute(
            """
            insert into regulation_build (snapshot_id, chunk_table, embed_table, meta_table,
                                          chunk_count, searchable_count, vector_count, status,
                                          source_fingerprint)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (snapshot_id) do update set
              chunk_table = excluded.chunk_table, embed_table = excluded.embed_table,
              meta_table = excluded.meta_table, chunk_count = excluded.chunk_count,
              searchable_count = excluded.searchable_count, vector_count = excluded.vector_count,
              status = excluded.status, source_fingerprint = excluded.source_fingerprint,
              built_at = now()
            """,
            (snapshot, tables.chunks, tables.embeddings, tables.meta, chunks, searchable, vectors,
             status, source_fingerprint()),
        )
        conn.commit()


def activate(tables: Tables, live: Tables, *, allow_shrink: bool = False) -> None:
    """Rename the built tables over the live names, in one transaction."""
    if not allow_shrink:
        with psycopg.connect(index_url()) as conn:
            if exists(conn, live.chunks):
                built = conn.execute(f"select count(*) from {tables.chunks}").fetchone()[0]
                current = conn.execute(f"select count(*) from {live.chunks}").fetchone()[0]
                if built < current * 0.9:
                    raise ValueError(
                        f"activate: {built:,} chunks would replace {current:,}; pass --allow-shrink"
                    )
    with psycopg.connect(index_url()) as conn:
        with conn.cursor() as cursor:
            for built, target in zip(
                (tables.chunks, tables.embeddings, tables.meta, tables.stems),
                (live.chunks, live.embeddings, live.meta, live.stems),
                strict=True,
            ):
                cursor.execute(f"drop table if exists {target}__old")
                cursor.execute(f"alter table if exists {target} rename to {target}__old")
                cursor.execute(f"alter table {built} rename to {target}")
        conn.commit()


def stems_table(chunks: str) -> str:
    return f"{chunks}_stems"


def exists(conn: psycopg.Connection, table: str) -> bool:
    return bool(conn.execute("select to_regclass(%s)", (table_name(table),)).fetchone()[0])


def chunk_row(value: Chunk, snapshot: str) -> tuple:
    return (
        value.chunk_id,
        snapshot,
        value.document_id,
        value.text_sha256,
        value.source_address,
        value.address,
        0,
        1,
        value.kind,
        value.label,
        value.heading,
        value.title,
        value.citation,
        value.issuer,
        value.doc_status,
        value.valid_from,
        value.valid_to,
        value.body,
        _md5(value.body),
        len(value.body),
        value.context_text,
        _md5(value.context_text),
        value.token_count,
        value.searchable,
        value.flags,
    )


def _md5(text: str) -> str:
    from .chunks import md5

    return md5(text)
