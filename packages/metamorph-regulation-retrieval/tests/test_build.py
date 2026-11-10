"""A build records the model that made its vectors, so a refresh reuses the live build's vectors only when they are the
same model's.

Needs METAMORPH_RETRIEVAL_TEST_DATABASE_URL, as test_store.py does; skipped without it.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql

from metamorph_regulation_retrieval.indexing import build as builder
from metamorph_regulation_retrieval.indexing.build import Tables
from metamorph_regulation_retrieval.indexing.chunks import CHUNK_DDL
from metamorph_regulation_retrieval.indexing.embed import EMBED_DDL

pytestmark = pytest.mark.database

SERVER_URL = os.environ.get("METAMORPH_RETRIEVAL_TEST_DATABASE_URL")
DIMENSION = 3
LIVE = Tables("regulation_chunk_live", "regulation_emb_live", "regulation_meta_live")
SNAPSHOT = "2026-01-01"
INSERT_CHUNK = (
    "INSERT INTO {table} (chunk_id, snapshot_id, document_id, text_sha256, source_address, address, kind, title, "
    "citation, issuer, doc_status, body, body_md5, body_chars, context_text, context_hash, token_count, searchable, "
    "flags) VALUES (%s, 's', 'd', 'h', 'a', 'a', 'ayat', 't', 'c', 'ojk', 'in_force', %s, 'm', 1, %s, 'h', 1, true, "
    "'{{}}')"
)


@pytest.fixture
def url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    if not SERVER_URL:
        pytest.skip("METAMORPH_RETRIEVAL_TEST_DATABASE_URL is not set")
    name = f"metamorph_build_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(SERVER_URL, autocommit=True) as server:
        server.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    target = psycopg.conninfo.make_conninfo(SERVER_URL, dbname=name)
    monkeypatch.setenv("METAMORPH_REGULATION_INDEX_URL", target)
    monkeypatch.setattr(builder, "source_fingerprint", lambda: "0:0:none")
    try:
        with psycopg.connect(target) as conn:
            conn.execute("CREATE EXTENSION vector")
        yield target
    finally:
        with psycopg.connect(SERVER_URL, autocommit=True) as server:
            server.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def write(url: str, tables: Tables, chunk_ids: list[str]) -> None:
    with psycopg.connect(url) as conn:
        conn.execute(CHUNK_DDL.format(table=tables.chunks))
        conn.execute(EMBED_DDL.format(table=tables.embeddings, dim=DIMENSION))
        for chunk_id in chunk_ids:
            conn.execute(INSERT_CHUNK.format(table=tables.chunks), (chunk_id, chunk_id, chunk_id))
            conn.execute(f"INSERT INTO {tables.embeddings} VALUES (%s, %s::vector)", (chunk_id, "[1,0,0]"))


def recorded(url: str, snapshot: str) -> tuple[str | None, str]:
    with psycopg.connect(url) as conn:
        return conn.execute("SELECT model, status FROM regulation_build WHERE snapshot_id = %s", (snapshot,)).fetchone()


def test_a_build_records_the_model_that_made_its_vectors(url: str) -> None:
    tables = Tables.for_snapshot(SNAPSHOT)
    write(url, tables, ["a"])

    builder.record(SNAPSHOT, tables, "ready", "bge_m3")

    assert recorded(url, SNAPSHOT) == ("bge_m3", "ready")
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT vector_count FROM regulation_build").fetchone()[0] == 1


def test_the_live_builds_embedding_table_and_model_are_read(url: str) -> None:
    tables = Tables.for_snapshot(SNAPSHOT)
    write(url, tables, ["a"])
    write(url, LIVE, ["a"])
    builder.record(SNAPSHOT, tables, "ready", "bge_m3")

    assert builder.live_vectors(LIVE) is None  # nothing is live yet

    builder.record(SNAPSHOT, LIVE, "live", builder.snapshot_model(SNAPSHOT))

    assert builder.live_vectors(LIVE) == (LIVE.embeddings, "bge_m3")


def test_a_build_recorded_before_models_were_is_bge_m3(url: str) -> None:
    tables = Tables.for_snapshot(SNAPSHOT)
    write(url, tables, ["a"])
    write(url, LIVE, ["a"])
    builder.record(SNAPSHOT, LIVE, "live", "bge_m3")
    with psycopg.connect(url) as conn:  # as the alter that added the column left the first builds
        conn.execute("UPDATE regulation_build SET model = NULL")

    assert builder.live_vectors(LIVE) == (LIVE.embeddings, "bge_m3")
    assert builder.snapshot_model(SNAPSHOT) == "bge_m3"


def test_a_live_build_without_its_vectors_reuses_nothing(url: str) -> None:
    tables = Tables.for_snapshot(SNAPSHOT)
    write(url, tables, ["a"])
    write(url, LIVE, ["a"])
    builder.record(SNAPSHOT, LIVE, "live", "bge_m3")
    with psycopg.connect(url) as conn:
        conn.execute(f"DROP TABLE {LIVE.embeddings}")

    assert builder.live_vectors(LIVE) is None
