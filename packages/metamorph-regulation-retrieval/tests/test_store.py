"""The store over PostgreSQL: filters are applied while candidates are found, and `in_force_on` keeps what was in
force that day.

Set METAMORPH_RETRIEVAL_TEST_DATABASE_URL to a server you may create databases on (see the market's conftest). Each
run gets a throwaway database with pgvector, dropped afterwards; without the variable these tests are skipped.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import date

import psycopg
import pytest
from psycopg import sql

from metamorph_regulation_retrieval.domain.filters import NO_FILTERS, Filters
from metamorph_regulation_retrieval.indexing.build import stems_table
from metamorph_regulation_retrieval.indexing.chunks import CHUNK_DDL, META_DDL, STEMS_DDL
from metamorph_regulation_retrieval.indexing.embed import EMBED_DDL, index_vectors
from metamorph_regulation_retrieval.store import BARE, COLUMNS, SEARCH, PostgresStore

pytestmark = pytest.mark.database

SERVER_URL = os.environ.get("METAMORPH_RETRIEVAL_TEST_DATABASE_URL")
TABLES = {"chunk_table": "regulation_chunk_live", "embed_table": "regulation_emb_live",
          "meta_table": "regulation_meta_live"}
DIMENSION = 3
QUESTION = [1.0, 0.0, 0.0]
READ_ONLY = "-c default_transaction_read_only=on -c statement_timeout=8000"  # as the wiring connects

# document id: kind, issuer, status, effective_on, revoked_on
DOCUMENTS = {
    "ojk:pojk:2024:40": ("regulation", "ojk", "in_force", date(2025, 1, 1), None),
    "ojk:pojk:2022:10": ("regulation", "ojk", "revoked", date(2022, 7, 4), date(2025, 1, 1)),
    "ojk:pojk:2016:77": ("regulation", "ojk", "revoked", date(2016, 12, 29), None),  # revoked, nobody says when
    "dsnmui:fatwa:117": ("fatwa", "dsnmui", "unknown", None, None),
}
# chunk: document, address, valid_to, searchable, vector (the closer to QUESTION, the better), wording
CHUNKS = [
    ("ojk:pojk:2016:77", "pasal-1", None, True, [1.0, 0.0, 0.0], "Penyelenggara wajib berbentuk badan hukum."),
    ("ojk:pojk:2022:10", "pasal-5", None, True, [0.99, 0.1, 0.0], "Modal disetor paling sedikit Rp25.000.000.000,00."),
    ("ojk:pojk:2024:40", "pasal-137/ayat-3", date(2026, 6, 1), True, [0.98, 0.2, 0.0],  # amended on 2026-06-01
     "Batas maksimum pendanaan kepada setiap penerima dana."),
    ("ojk:pojk:2024:40", "pasal-137/ayat-4", None, True, [0.95, 0.3, 0.0], "Pendanaan produktif sampai Rp5 miliar."),
    ("ojk:pojk:2024:40", "penjelasan/pasal-1", None, False, [1.0, 0.0, 0.0], "Cukup jelas."),
    ("dsnmui:fatwa:117", "diktum-kedua", None, True, [0.5, 0.8, 0.0],
     "Dana yang berasal dari denda diperuntukkan sebagai dana sosial."),
]


@pytest.fixture(scope="module")
def store() -> Iterator[PostgresStore]:
    if not SERVER_URL:
        pytest.skip("METAMORPH_RETRIEVAL_TEST_DATABASE_URL is not set")
    name = f"metamorph_regulation_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(SERVER_URL, autocommit=True) as server:
        server.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = psycopg.conninfo.make_conninfo(SERVER_URL, dbname=name)
    try:
        with psycopg.connect(url) as connection:
            seed(connection)
        yield PostgresStore(url, dimension=DIMENSION, options=READ_ONLY, **TABLES)
    finally:
        with psycopg.connect(SERVER_URL, autocommit=True) as server:
            server.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def seed(connection: psycopg.Connection) -> None:
    connection.execute("CREATE EXTENSION vector")
    connection.execute(CHUNK_DDL.format(table=TABLES["chunk_table"]))
    connection.execute(META_DDL.format(table=TABLES["meta_table"]))
    connection.execute(EMBED_DDL.format(table=TABLES["embed_table"], dim=DIMENSION))
    for document, (kind, issuer, status, effective_on, revoked_on) in DOCUMENTS.items():
        connection.execute(
            f"INSERT INTO {TABLES['meta_table']} (document_id, kind, citation, title, issuer, status, effective_on, "
            "published_at, revoked_on) VALUES (%s, %s, %s, %s, %s, %s, %s, now(), %s)",
            (document, kind, document, document, issuer, status, effective_on, revoked_on))
    for document, address, valid_to, searchable, vector, wording in CHUNKS:
        chunk_id = f"{document}|{address}"
        kind, issuer, status, _, _ = DOCUMENTS[document]
        connection.execute(
            f"INSERT INTO {TABLES['chunk_table']} (chunk_id, snapshot_id, document_id, text_sha256, source_address, "
            "address, kind, title, citation, issuer, doc_status, valid_to, body, body_md5, body_chars, context_text, "
            "context_hash, token_count, searchable, flags) "
            "VALUES (%s, 's', %s, 'h', %s, %s, 'ayat', %s, %s, %s, %s, %s, %s, 'm', 7, %s, 'h', 1, %s, '{}')",
            (chunk_id, document, address, address, document, document, issuer, status, valid_to, wording, wording,
             searchable))
        connection.execute(f"INSERT INTO {TABLES['embed_table']} VALUES (%s, %s::vector)", (chunk_id, str(vector)))
    # as the build counts them; with five units, a stem in more than one (dana: three) is common here
    connection.execute(STEMS_DDL.format(stems=stems_table(TABLES["chunk_table"]), chunks=TABLES["chunk_table"],
                                        share=0.25))


def found(store: PostgresStore, filters: Filters = NO_FILTERS, limit: int = 10) -> list[str]:
    return [f"{passage.document_id}#{passage.address}" for passage, _ in store.by_meaning(QUESTION, limit, filters)]


def test_search_ranks_searchable_chunks_by_meaning(store: PostgresStore) -> None:
    assert found(store) == ["ojk:pojk:2016:77#pasal-1", "ojk:pojk:2022:10#pasal-5",
                            "ojk:pojk:2024:40#pasal-137/ayat-3", "ojk:pojk:2024:40#pasal-137/ayat-4",
                            "dsnmui:fatwa:117#diktum-kedua"]


def test_a_filter_is_applied_before_the_limit(store: PostgresStore) -> None:
    assert found(store, Filters(kinds=frozenset({"fatwa"})), limit=1) == ["dsnmui:fatwa:117#diktum-kedua"]
    assert found(store, Filters(issuers=frozenset({"dsnmui"})), limit=1) == ["dsnmui:fatwa:117#diktum-kedua"]
    assert found(store, Filters(documents=("ojk:pojk:2024:40",)), limit=1) == ["ojk:pojk:2024:40#pasal-137/ayat-3"]


def test_in_force_on_keeps_what_was_in_force_that_day(store: PostgresStore) -> None:
    assert found(store, Filters(in_force_on=date(2024, 6, 1))) == [
        "ojk:pojk:2022:10#pasal-5",  # revoked only from 2025; POJK 40/2024 not yet in force
        "dsnmui:fatwa:117#diktum-kedua",  # no effective date: kept
    ]
    assert found(store, Filters(in_force_on=date(2025, 3, 1))) == [
        "ojk:pojk:2024:40#pasal-137/ayat-3", "ojk:pojk:2024:40#pasal-137/ayat-4", "dsnmui:fatwa:117#diktum-kedua"]


def test_a_provision_ends_on_its_valid_to(store: PostgresStore) -> None:
    assert found(store, Filters(in_force_on=date(2026, 6, 1), documents=("ojk:pojk:2024:40",))) == [
        "ojk:pojk:2024:40#pasal-137/ayat-4"]


def test_the_index_dates_revocations_and_matches_words(store: PostgresStore) -> None:
    assert store.dates_revocations() is True and store.matches_words() is True


def test_by_words_a_unit_holds_at_least_half_the_questions_stems(store: PostgresStore) -> None:
    def by_words(question: str, filters: Filters = NO_FILTERS) -> list[str]:
        return [f"{passage.document_id}#{passage.address}" for passage, _ in store.by_words(question, 10, filters)]

    assert by_words("didenda secara sosial") == ["dsnmui:fatwa:117#diktum-kedua"]  # its stems, not its exact words
    assert by_words("denda produktif miliar") == ["ojk:pojk:2024:40#pasal-137/ayat-4"]  # two of three
    assert by_words("denda modal badan") == []  # one of three, in each unit: not a match
    assert by_words("what is the dana sosial") == ["dsnmui:fatwa:117#diktum-kedua"]  # a stem no unit holds can't count
    assert by_words("dana") == []  # common: in most units, so it picks none
    assert by_words("dana sosial") == ["dsnmui:fatwa:117#diktum-kedua"]  # but it counts: two of two
    assert by_words("denda sosial", Filters(kinds=frozenset({"regulation"}))) == []  # and the filters hold


def test_an_index_built_before_revocations_were_dated_keeps_todays_status(store: PostgresStore) -> None:
    with psycopg.connect(store.url) as connection:
        connection.execute(f"CREATE TABLE IF NOT EXISTS regulation_meta_old AS SELECT * FROM {TABLES['meta_table']}")
        connection.execute("ALTER TABLE regulation_meta_old DROP COLUMN IF EXISTS revoked_on")
    old = PostgresStore(store.url, dimension=DIMENSION, **(TABLES | {"meta_table": "regulation_meta_old"}))

    assert old.dates_revocations() is False
    assert found(old, Filters(in_force_on=date(2024, 6, 1))) == ["dsnmui:fatwa:117#diktum-kedua"]


def test_the_search_uses_the_graph_the_build_makes(store: PostgresStore) -> None:
    with psycopg.connect(store.url) as connection:
        index_vectors(connection, TABLES["embed_table"], DIMENSION)
        connection.execute("SET LOCAL enable_seqscan = off")
        query = SEARCH.format(columns=COLUMNS, bare=BARE, embed=TABLES["embed_table"], chunk=TABLES["chunk_table"],
                              meta=TABLES["meta_table"], dim=DIMENSION, where="")
        plan = "\n".join(row[0] for row in connection.execute(
            "EXPLAIN " + query, {"vector": str(QUESTION), "depth": 50, "limit": 10}))

    assert f"{TABLES['embed_table']}_hnsw" in plan


def test_the_sessions_keep_the_urls_own_options() -> None:
    from metamorph_regulation_retrieval.store import session_options

    url = "postgresql://reader@db/metamorph?options=-c%20search_path%3Dretrieval_regulation,public"
    assert session_options(url, READ_ONLY, {}) == f"-c search_path=retrieval_regulation,public {READ_ONLY}"
    assert session_options("postgresql://reader@db/metamorph", READ_ONLY, {}) == READ_ONLY
    schema = {"PGOPTIONS": "-c search_path=retrieval_regulation,public"}
    assert session_options("postgresql://reader@db/metamorph", READ_ONLY, schema) == (
        f"-c search_path=retrieval_regulation,public {READ_ONLY}")


def test_an_index_in_its_own_schema_is_found_through_the_urls_search_path(store: PostgresStore) -> None:
    with psycopg.connect(store.url, autocommit=True) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS retrieval_regulation")
        for table in TABLES.values():
            connection.execute(f"CREATE TABLE IF NOT EXISTS retrieval_regulation.{table} AS SELECT * FROM {table}")
        connection.execute(f"CREATE TABLE IF NOT EXISTS retrieval_regulation.{stems_table(TABLES['chunk_table'])} AS "
                           f"SELECT * FROM {stems_table(TABLES['chunk_table'])}")
    url = psycopg.conninfo.make_conninfo(store.url, options="-c search_path=retrieval_regulation,public")
    schema = PostgresStore(url, dimension=DIMENSION, options=READ_ONLY, **TABLES)

    assert schema.matches_words() and schema.dates_revocations()
    assert [p.address for p, _ in schema.by_words("denda sosial", 5)] == ["diktum-kedua"]
