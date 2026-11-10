"""Vectors move between builds by chunk: a chunk's id names its document, address and wording, so its vector is the
same wherever that chunk is built. A build seeded with another's vectors embeds only what they don't cover.

Needs METAMORPH_RETRIEVAL_TEST_DATABASE_URL, as test_store.py does; skipped without it.
"""

from __future__ import annotations

import io
import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql

from metamorph_regulation_retrieval.indexing.chunks import CHUNK_DDL
from metamorph_regulation_retrieval.indexing.embed import (
    EMBED_DDL,
    embed,
    export_vectors,
    import_vectors,
    seed_vectors,
)

pytestmark = pytest.mark.database

SERVER_URL = os.environ.get("METAMORPH_RETRIEVAL_TEST_DATABASE_URL")
DIMENSION = 3


@pytest.fixture
def connection() -> Iterator[psycopg.Connection]:
    if not SERVER_URL:
        pytest.skip("METAMORPH_RETRIEVAL_TEST_DATABASE_URL is not set")
    name = f"metamorph_vectors_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(SERVER_URL, autocommit=True) as server:
        server.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        with psycopg.connect(psycopg.conninfo.make_conninfo(SERVER_URL, dbname=name)) as conn:
            conn.execute("CREATE EXTENSION vector")
            yield conn
    finally:
        with psycopg.connect(SERVER_URL, autocommit=True) as server:
            server.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def chunks(conn: psycopg.Connection, table: str, rows: list[tuple[str, bool]]) -> None:
    conn.execute(CHUNK_DDL.format(table=table))
    for chunk_id, searchable in rows:
        conn.execute(
            f"INSERT INTO {table} (chunk_id, snapshot_id, document_id, text_sha256, source_address, address, kind, "
            "title, citation, issuer, doc_status, body, body_md5, body_chars, context_text, context_hash, token_count, "
            "searchable, flags) VALUES (%s, 's', 'd', 'h', 'a', 'a', 'ayat', 't', 'c', 'ojk', 'in_force', %s, 'm', 1, "
            "%s, 'h', 1, %s, '{}')", (chunk_id, chunk_id, chunk_id, searchable))


class Model:
    def __init__(self) -> None:
        self.embedded: list[str] = []

    def encode(self, texts, batch_size, normalize_embeddings, show_progress_bar):  # noqa: ANN001, ANN201
        self.embedded += texts
        return [[0.0, 0.0, 1.0] for _ in texts]


def vectors(conn: psycopg.Connection, table: str) -> dict[str, str]:
    return dict(conn.execute(f"SELECT chunk_id, embedding::text FROM {table} ORDER BY chunk_id").fetchall())


def test_vectors_move_by_chunk(connection: psycopg.Connection) -> None:
    chunks(connection, "chunk_old", [("a", True), ("b", True), ("gone", True)])
    connection.execute(EMBED_DDL.format(table="emb_old", dim=DIMENSION))
    for chunk_id, vector in [("a", "[1,0,0]"), ("b", "[0,1,0]"), ("gone", "[1,1,0]")]:
        connection.execute("INSERT INTO emb_old VALUES (%s, %s::vector)", (chunk_id, vector))

    exported = io.BytesIO()
    assert export_vectors(connection, "chunk_old", "emb_old", exported) == 3

    chunks(connection, "chunk_new", [("a", True), ("b", False), ("new", True)])  # b no longer searched; new is new
    connection.execute(EMBED_DDL.format(table="emb_new", dim=DIMENSION))
    assert import_vectors(connection, "chunk_new", "emb_new", io.BytesIO(exported.getvalue()), DIMENSION) == 1
    assert vectors(connection, "emb_new") == {"a": "[1,0,0]"}

    model = Model()
    assert embed(connection, "chunk_new", "emb_new", model) == 1
    assert model.embedded == ["new"]  # only what the seed didn't cover
    assert vectors(connection, "emb_new") == {"a": "[1,0,0]", "new": "[0,0,1]"}


def test_a_build_takes_the_live_builds_vectors_where_it_can(connection: psycopg.Connection) -> None:
    chunks(connection, "chunk_live", [("a", True), ("b", True), ("gone", True)])
    connection.execute(EMBED_DDL.format(table="emb_live", dim=DIMENSION))
    for chunk_id, vector in [("a", "[1,0,0]"), ("b", "[0,1,0]"), ("gone", "[1,1,0]")]:
        connection.execute("INSERT INTO emb_live VALUES (%s, %s::vector)", (chunk_id, vector))

    chunks(connection, "chunk_build", [("a", True), ("b", False), ("new", True)])  # b no longer searched; new is new
    connection.execute(EMBED_DDL.format(table="emb_build", dim=DIMENSION))
    assert seed_vectors(connection, "chunk_build", "emb_build", "emb_live") == 1
    assert vectors(connection, "emb_build") == {"a": "[1,0,0]"}
    assert seed_vectors(connection, "chunk_build", "emb_build", "emb_live") == 0  # a is there already

    model = Model()
    assert embed(connection, "chunk_build", "emb_build", model) == 1
    assert model.embedded == ["new"]
