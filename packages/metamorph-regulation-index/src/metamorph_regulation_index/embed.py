"""The embedding model: one choice, one batch loop, one table.

bge-m3 at 512 tokens, normalised, no instruction prefix. The same settings the
benchmark used, so an index built here is comparable with the numbers we quote.
"""

from __future__ import annotations

import os

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
where e.chunk_id is null
order by c.chunk_id
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


def create_table(conn: psycopg.Connection, table: str, dim: int) -> None:
    conn.execute(f"drop table if exists {table}")
    conn.execute(EMBED_DDL.format(table=table, dim=dim))


def embed(
    conn: psycopg.Connection,
    chunk_table: str,
    embed_table: str,
    model,
    *,
    batch: int = BATCH,
    limit: int | None = None,
) -> int:
    """Embed every chunk that has no vector yet. Resumable: rerunning skips them."""
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
