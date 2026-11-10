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
from metamorph_regulation_retrieval.indexing.build import links_table, stems_table
from metamorph_regulation_retrieval.indexing.chunks import CHUNK_DDL, LINK_DDL, META_DDL, STEMS_DDL
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
HISTORY = '[{"status": "revoked", "effective_from": "2025-01-01", "source": "links"}]'
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
# link: type, from document, from address, to document, to address, effective on
LINKS = [
    ("revokes", "ojk:pojk:2024:40", None, "ojk:pojk:2022:10", None, date(2025, 1, 1)),
    ("revokes", "ojk:pojk:2026:9", None, "ojk:pojk:2024:40", None, date(2024, 6, 1)),  # older, yet what changes it
    ("partly_revokes", "ojk:pojk:2023:22", None, "ojk:pojk:2022:10", "pasal-102", date(2023, 12, 1)),
    ("amends", "ojk:pojk:2025:1", "pasal-i", "ojk:pojk:2022:10", "pasal-5/ayat-1", date(2025, 3, 1)),
    ("amends", "ojk:pojk:2026:1", "pasal-i", "ojk:pojk:2022:10", "pasal-5", date(2026, 3, 1)),
    ("refers_to", "ojk:pojk:2022:10", "pasal-7", "ojk:pojk:2022:10", "pasal-5", date(2022, 7, 4)),  # inside it
    ("refers_to", "ojk:pojk:2024:40", "pasal-9", "ojk:pojk:2022:10", "pasal-5", date(2025, 1, 1)),
    ("refers_to", "ojk:pojk:2024:40", "pasal-9", "ojk:pojk:2022:10", None, date(2025, 1, 1)),
    ("legal_basis", "ojk:pojk:2022:10", None, "id:uu:2011:21", None, date(2022, 7, 4)),
    ("refers_to", "ojk:pojk:2022:10", "pasal-50", "ojk:pojk:2016:77", "pasal-1", date(2022, 7, 4)),  # a neighbour
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
            "published_at, revoked_on, status_history) VALUES (%s, %s, %s, %s, %s, %s, %s, now(), %s, %s)",
            (document, kind, document, document, issuer, status, effective_on, revoked_on,
             HISTORY if revoked_on else None))
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
    table = links_table(TABLES["chunk_table"])
    connection.execute(LINK_DDL.format(table=table))
    for type_, from_document, from_address, to_document, to_address, effective_on in LINKS:
        connection.execute(f"INSERT INTO {table} VALUES (%s, %s, %s, %s, %s, %s, 'high')",
                           (type_, from_document, from_address, to_document, to_address, effective_on))
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


def linked(store: PostgresStore, document: str, address: str | None = None, *, incoming: bool = True,
           outgoing: bool = True, types: list[str] | None = None, limit: int = 25, offset: int = 0) -> list[tuple]:
    rows = store.links(document, address, incoming=incoming, outgoing=outgoing, types=types or [], limit=limit,
                       offset=offset)
    return [(row.type, row.from_document, row.from_address, row.to_document, row.to_address) for row in rows]


def test_a_documents_links_are_those_with_other_documents(store: PostgresStore) -> None:
    found = linked(store, "ojk:pojk:2022:10")

    assert ("refers_to", "ojk:pojk:2022:10", "pasal-7", "ojk:pojk:2022:10", "pasal-5") not in found
    assert len(found) == 8


def test_what_changes_a_document_comes_first_and_the_newest_of_each_type_leads(store: PostgresStore) -> None:
    found = linked(store, "ojk:pojk:2022:10", incoming=True, outgoing=False)

    assert [row[:2] for row in found[:4]] == [("revokes", "ojk:pojk:2024:40"), ("partly_revokes", "ojk:pojk:2023:22"),
                                              ("amends", "ojk:pojk:2026:1"), ("amends", "ojk:pojk:2025:1")]


def test_what_changes_a_text_comes_before_what_that_text_changes(store: PostgresStore) -> None:
    found = linked(store, "ojk:pojk:2024:40")

    assert found[0] == ("revokes", "ojk:pojk:2026:9", None, "ojk:pojk:2024:40", None)
    assert found[1] == ("revokes", "ojk:pojk:2024:40", None, "ojk:pojk:2022:10", None)


def test_a_provision_has_the_links_on_it_and_inside_it(store: PostgresStore) -> None:
    found = linked(store, "ojk:pojk:2022:10", "pasal-5", incoming=True, outgoing=False)

    assert ("amends", "ojk:pojk:2026:1", "pasal-i", "ojk:pojk:2022:10", "pasal-5") in found
    assert ("amends", "ojk:pojk:2025:1", "pasal-i", "ojk:pojk:2022:10", "pasal-5/ayat-1") in found


def test_a_provision_has_what_its_own_document_says_of_it(store: PostgresStore) -> None:
    found = linked(store, "ojk:pojk:2022:10", "pasal-5", incoming=True, outgoing=False)

    assert ("refers_to", "ojk:pojk:2022:10", "pasal-7", "ojk:pojk:2022:10", "pasal-5") in found


def test_what_changes_the_document_or_article_holding_a_provision_is_a_link_of_that_provision(
        store: PostgresStore) -> None:
    found = linked(store, "ojk:pojk:2022:10", "pasal-5/ayat-1", incoming=True, outgoing=False)

    assert ("revokes", "ojk:pojk:2024:40", None, "ojk:pojk:2022:10", None) in found
    assert ("amends", "ojk:pojk:2026:1", "pasal-i", "ojk:pojk:2022:10", "pasal-5") in found


def test_what_merely_cites_the_whole_document_is_no_link_of_a_provision(store: PostgresStore) -> None:
    found = linked(store, "ojk:pojk:2022:10", "pasal-5/ayat-1", incoming=True, outgoing=False)

    assert ("refers_to", "ojk:pojk:2024:40", "pasal-9", "ojk:pojk:2022:10", None) not in found
    assert ("refers_to", "ojk:pojk:2024:40", "pasal-9", "ojk:pojk:2022:10", "pasal-5") not in found


def test_a_neighbouring_address_is_not_a_part(store: PostgresStore) -> None:
    assert linked(store, "ojk:pojk:2022:10", "pasal-5", incoming=False, outgoing=True) == []


def test_links_narrow_to_the_types_and_direction_asked(store: PostgresStore) -> None:
    assert linked(store, "ojk:pojk:2022:10", outgoing=False, types=["revokes"]) == [
        ("revokes", "ojk:pojk:2024:40", None, "ojk:pojk:2022:10", None)]
    assert linked(store, "ojk:pojk:2022:10", incoming=False, types=["legal_basis"]) == [
        ("legal_basis", "ojk:pojk:2022:10", None, "id:uu:2011:21", None)]


def test_links_page_without_repeating(store: PostgresStore) -> None:
    every = linked(store, "ojk:pojk:2022:10")

    assert linked(store, "ojk:pojk:2022:10", limit=3) + linked(store, "ojk:pojk:2022:10", limit=5, offset=3) == every


def test_a_document_not_published_has_links_all_the_same(store: PostgresStore) -> None:
    assert linked(store, "id:uu:2011:21") == [("legal_basis", "ojk:pojk:2022:10", None, "id:uu:2011:21", None)]


def test_the_store_says_whether_the_index_holds_links(store: PostgresStore) -> None:
    assert store.holds_links() is True
    assert PostgresStore(store.url, dimension=DIMENSION, options=READ_ONLY, chunk_table="regulation_chunk_old",
                         embed_table=TABLES["embed_table"], meta_table=TABLES["meta_table"]).holds_links() is False


def test_a_documents_status_history_is_read_with_its_card(store: PostgresStore) -> None:
    assert store.document("ojk:pojk:2022:10")["status_history"] == [
        {"status": "revoked", "effective_from": "2025-01-01", "source": "links"}]


def test_an_index_without_a_status_history_still_gives_the_card(store: PostgresStore) -> None:
    assert store.document("dsnmui:fatwa:117")["status_history"] is None


def test_a_provision_reads_its_own_status_where_the_index_holds_one(store: PostgresStore) -> None:
    with psycopg.connect(store.url) as connection:
        connection.execute(f"CREATE TABLE IF NOT EXISTS regulation_chunk_own AS SELECT * FROM {TABLES['chunk_table']}")
        connection.execute("UPDATE regulation_chunk_own SET status = 'amended' WHERE address = 'pasal-137/ayat-3'")
        connection.execute(f"CREATE TABLE IF NOT EXISTS regulation_chunk_bare AS SELECT * FROM {TABLES['chunk_table']}")
        connection.execute("ALTER TABLE regulation_chunk_bare DROP COLUMN IF EXISTS status")
    own = PostgresStore(store.url, dimension=DIMENSION, **(TABLES | {"chunk_table": "regulation_chunk_own"}))
    bare = PostgresStore(store.url, dimension=DIMENSION, **(TABLES | {"chunk_table": "regulation_chunk_bare"}))

    assert own.read("ojk:pojk:2024:40", "pasal-137/ayat-3").status == "amended"
    assert own.read("ojk:pojk:2024:40", "pasal-137/ayat-4").status == "in_force"  # none of its own: its document's
    assert bare.read("ojk:pojk:2024:40", "pasal-137/ayat-3").status == "in_force"  # an index built before
