"""The embedding model: one choice, one batch loop, one table.

bge-m3 at 512 tokens, normalised, no instruction prefix. The same settings the
benchmark used, so an index built here is comparable with the numbers we quote.
"""

from __future__ import annotations

import gzip
import os
import urllib.request
from typing import BinaryIO

import psycopg
from pgvector.psycopg import register_vector

MODELS = {
    "bge_m3": {"hf": "BAAI/bge-m3", "dim": 1024},
}
DEFAULT_MODEL = "bge_m3"
MAX_SEQ_LEN = 512
BATCH = 32
DEVICE = "METAMORPH_REGULATION_DEVICE"

EMBED_DDL = """
create table {table} (
  chunk_id text primary key,
  embedding vector({dim}) not null
)
"""

SELECT = """
select c.chunk_id, c.context_text
from {chunk} c
left join {embed} e using (chunk_id)
where c.searchable and e.chunk_id is null
order by length(c.context_text), c.chunk_id
"""


def load_model(name: str = DEFAULT_MODEL, max_seq_len: int = MAX_SEQ_LEN):
    if name not in MODELS:
        raise ValueError(f"{name}: not a known model; known: {', '.join(sorted(MODELS))}")
    try:
        from sentence_transformers import SentenceTransformer
    except ModuleNotFoundError as error:  # pragma: no cover - the extra is optional
        raise RuntimeError("install the embeddings extra to build an index") from error

    model = SentenceTransformer(MODELS[name]["hf"], device=os.environ.get(DEVICE) or None)
    model.max_seq_length = max_seq_len
    return model


# The graph the provider searches (store.py): half-precision vectors, cosine distance. The query's
# expression must be this one for the planner to use it.
VECTOR_INDEX = (
    "create index if not exists {table}_hnsw on {table} "
    "using hnsw ((embedding::halfvec({dim})) halfvec_cosine_ops)"
)


def create_table(conn: psycopg.Connection, table: str, dim: int) -> None:
    conn.execute(f"drop table if exists {table}")
    conn.execute(EMBED_DDL.format(table=table, dim=dim))


def index_vectors(conn: psycopg.Connection, table: str, dim: int) -> None:
    """Build the HNSW graph once every vector is in: building it first would slow every insert."""
    conn.execute(VECTOR_INDEX.format(table=table, dim=dim))


def embed(
    conn: psycopg.Connection,
    chunk_table: str,
    embed_table: str,
    model,
    *,
    batch: int = BATCH,
    limit: int | None = None,
) -> int:
    """Embed every searchable chunk that has no vector yet. Resumable: rerunning skips them.

    Shortest first: a batch is padded to its longest text, so batches of similar length waste little.
    """
    register_vector(conn)
    rows = conn.execute(SELECT.format(chunk=chunk_table, embed=embed_table)).fetchall()
    if limit:
        rows = rows[:limit]
    if not rows:
        return 0

    written = 0
    for start in range(0, len(rows), batch):
        block = rows[start : start + batch]
        vectors = model.encode(
            [text for _, text in block],
            batch_size=batch,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        with conn.cursor() as cursor:
            cursor.executemany(
                f"insert into {embed_table} (chunk_id, embedding) values (%s, %s) "
                "on conflict (chunk_id) do nothing",
                [(chunk_id, vector) for (chunk_id, _), vector in zip(block, vectors, strict=True)],
            )
        conn.commit()
        written += len(block)
        print(f"embedded {written}/{len(rows)}", flush=True)
    return written


# Vectors between builds. A chunk's id names its document, its text's hash, its address and the hash of what the model
# reads, so its vector is the same wherever the chunk is built: a build can take another's (one made where embedding is
# fast) and embed only the chunks they don't cover. A refresh takes them straight from the live build's table, by id
# (seed_vectors), so it embeds only the new and changed chunks. The file is gzipped COPY text: chunk id, tab, vector.

EXPORT = """
copy (select e.chunk_id, e.embedding from {embed} e join {chunk} c using (chunk_id) where c.searchable
      order by e.chunk_id) to stdout
"""


def export_vectors(conn: psycopg.Connection, chunk_table: str, embed_table: str, out: BinaryIO) -> int:
    """Write the searchable chunks' vectors to `out`; the number written."""
    written = 0
    with gzip.GzipFile(fileobj=out, mode="wb") as packed, conn.cursor() as cursor:
        with cursor.copy(EXPORT.format(embed=embed_table, chunk=chunk_table)) as copy:
            for block in copy:
                packed.write(block)
        written = cursor.execute(
            f"select count(*) from {embed_table} e join {chunk_table} c using (chunk_id) where c.searchable"
        ).fetchone()[0]
    return written


def import_vectors(conn: psycopg.Connection, chunk_table: str, embed_table: str, source: BinaryIO, dim: int) -> int:
    """Take, from `source`, the vectors of this build's searchable chunks; the number taken. Others are ignored."""
    with conn.cursor() as cursor:
        cursor.execute(f"create temporary table seed (chunk_id text, embedding vector({dim})) on commit drop")
        with gzip.GzipFile(fileobj=source, mode="rb") as packed, cursor.copy("copy seed from stdin") as copy:
            while block := packed.read(1 << 20):
                copy.write(block)
        cursor.execute(
            f"insert into {embed_table} (chunk_id, embedding) select s.chunk_id, s.embedding from seed s "
            f"join {chunk_table} c using (chunk_id) where c.searchable on conflict (chunk_id) do nothing"
        )
        taken = cursor.rowcount
    conn.commit()
    return taken


def seed_vectors(conn: psycopg.Connection, chunk_table: str, embed_table: str, source_embed_table: str) -> int:
    """Take, from another build's embedding table, the vectors of this build's searchable chunks; the number taken."""
    with conn.cursor() as cursor:
        cursor.execute(
            f"insert into {embed_table} (chunk_id, embedding) "
            f"select s.chunk_id, s.embedding from {source_embed_table} s "
            f"join {chunk_table} c using (chunk_id) where c.searchable on conflict (chunk_id) do nothing"
        )
        taken = cursor.rowcount
    conn.commit()
    return taken


def open_vectors(location: str) -> BinaryIO:
    """A file's path, or an http(s) URL (a presigned S3 link): the task needs no credentials of its own."""
    if location.startswith(("https://", "http://")):
        return urllib.request.urlopen(location, timeout=300)  # noqa: S310 - the operator names it
    return open(location, "rb")
