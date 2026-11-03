"""Query the regulation index: candidate generation on the halfvec index, then a
full-precision rescore of those candidates.

The halfvec index is half the size of the float one and fits a 4 GiB instance.
Rescoring the top candidates with the stored float vectors recovers the ranking
that quantisation costs, for a few milliseconds.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from metamorph_regulation_retrieval.domain.passage import Passage

CHUNK_TABLE = "METAMORPH_REGULATION_CHUNK_TABLE"
EMBED_TABLE = "METAMORPH_REGULATION_EMBED_TABLE"
META_TABLE = "METAMORPH_REGULATION_META_TABLE"

DEFAULT_CHUNK = "regulation_chunk_live"
DEFAULT_EMBED = "regulation_emb_live"
DEFAULT_META = "regulation_meta_live"

COLUMNS = """
c.chunk_id, c.document_id, c.address, c.title, c.citation, c.body,
m.kind, m.status, c.valid_from, c.valid_to, m.effective_on, m.promulgated_on,
m.published_at, c.issuer, m.family, m.number, m.year, m.citation as doc_citation
"""

BARE = """
chunk_id, document_id, address, title, citation, body,
kind, status, valid_from, valid_to, effective_on, promulgated_on,
published_at, issuer, family, number, year, doc_citation
"""

SEARCH = """
with candidates as (
  select {columns}, e.embedding as embedding
  from {embed} e
  join {chunk} c using (chunk_id)
  join {meta} m on m.document_id = c.document_id
  where c.searchable
  order by (e.embedding::halfvec({dim})) <=> (%s::vector)::halfvec({dim})
  limit %s
)
select {bare}, 1 - (embedding <=> %s::vector) as score
from candidates
order by embedding <=> %s::vector
limit %s
"""

READ = """
select {columns}
from {chunk} c
join {meta} m on m.document_id = c.document_id
where c.document_id = %s and c.address = %s
limit 1
"""

DOCUMENT = """
select document_id, kind, citation, title, issuer, status, family, number, year,
       promulgated_on, effective_on, published_at, aliases
from {meta}
where document_id = %s
"""

DOCUMENT_COLUMNS = (
    "document_id", "kind", "citation", "title", "issuer", "status", "family", "number",
    "year", "promulgated_on", "effective_on", "published_at", "aliases",
)


class PostgresStore:
    """The index database, read only."""

    def __init__(
        self,
        url: str,
        *,
        chunk_table: str | None = None,
        embed_table: str | None = None,
        meta_table: str | None = None,
        dimension: int = 1024,
        ef_search: int = 200,
    ) -> None:
        self.url = url
        self.chunk_table = _table(chunk_table or os.environ.get(CHUNK_TABLE, DEFAULT_CHUNK))
        self.embed_table = _table(embed_table or os.environ.get(EMBED_TABLE, DEFAULT_EMBED))
        self.meta_table = _table(meta_table or os.environ.get(META_TABLE, DEFAULT_META))
        self.dimension = dimension
        self.ef_search = ef_search

    def search(self, vector: Sequence[float], limit: int) -> list[tuple[Passage, float]]:
        depth = max(int(limit) * 4, 50)
        with psycopg.connect(self.url) as conn:
            register_vector(conn)
            conn.execute(f"set local hnsw.ef_search = {max(self.ef_search, depth)}")
            rows = conn.execute(
                SEARCH.format(
                    columns=COLUMNS, bare=BARE, embed=self.embed_table, chunk=self.chunk_table,
                    meta=self.meta_table, dim=self.dimension,
                ),
                (list(vector), depth, list(vector), list(vector), limit),
            ).fetchall()
        return [(_passage(row), float(row[18])) for row in rows]

    def read(self, document_id: str, address: str) -> Passage | None:
        with psycopg.connect(self.url) as conn:
            row = conn.execute(
                READ.format(columns=COLUMNS, chunk=self.chunk_table, meta=self.meta_table),
                (document_id, address),
            ).fetchone()
        return _passage(row) if row else None

    def document(self, document_id: str) -> dict[str, Any] | None:
        with psycopg.connect(self.url) as conn:
            row = conn.execute(
                DOCUMENT.format(meta=self.meta_table), (document_id,)
            ).fetchone()
        return dict(zip(DOCUMENT_COLUMNS, row, strict=True)) if row else None

    def published_at(self):
        with psycopg.connect(self.url) as conn:
            return conn.execute(f"select max(published_at) from {self.meta_table}").fetchone()[0]

    def ping(self) -> None:
        with psycopg.connect(self.url, connect_timeout=2) as conn:
            conn.execute(f"select 1 from {self.chunk_table} limit 1").fetchone()


def _passage(row: Sequence[Any]) -> Passage:
    return Passage(
        chunk_id=row[0],
        document_id=row[1],
        address=row[2],
        title=row[3],
        citation=row[4],
        text=row[5],
        doc_kind=row[6],
        doc_status=row[7],
        valid_from=row[8],
        valid_to=row[9],
        effective_on=row[10],
        promulgated_on=row[11],
        published_at=row[12],
        issuer=row[13],
        family=row[14],
        number=row[15],
        year=row[16],
        doc_citation=row[17],
    )


def _table(name: str) -> str:
    import re

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"{name!r} is not a table name")
    return name
