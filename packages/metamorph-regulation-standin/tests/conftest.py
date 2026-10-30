"""The read model is tested twice: in memory, and over PostgreSQL holding the same records.

Set METAMORPH_RETRIEVAL_TEST_DATABASE_URL to a server you may create databases on (see the market provider's
conftest). Each session gets a throwaway database, dropped afterwards; without the variable, those cases are skipped.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from memory_regulations import MemoryRegulations
from psycopg import sql

from metamorph_regulation_standin.adapters.postgres import PostgresRegulationReadModel
from metamorph_regulation_standin.application.ports import RegulationReadModel

SERVER_URL = os.environ.get("METAMORPH_RETRIEVAL_TEST_DATABASE_URL")
SCHEMA = Path(__file__).with_name("published.sql")


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    if not SERVER_URL:
        pytest.skip("METAMORPH_RETRIEVAL_TEST_DATABASE_URL is not set")
    name = f"metamorph_standin_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(SERVER_URL, autocommit=True) as server:
        server.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = psycopg.conninfo.make_conninfo(SERVER_URL, dbname=name)
    try:
        with psycopg.connect(url) as connection:
            connection.execute(SCHEMA.read_text(encoding="utf-8"))
            seed(connection, MemoryRegulations())
        yield url
    finally:
        with psycopg.connect(SERVER_URL, autocommit=True) as server:
            server.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.database)])
def read_model(request: pytest.FixtureRequest) -> Iterator[RegulationReadModel]:
    if request.param == "memory":
        yield MemoryRegulations()
        return
    with psycopg.connect(request.getfixturevalue("database_url")) as connection:
        yield PostgresRegulationReadModel(connection)


def seed(connection: psycopg.Connection, regulations: MemoryRegulations) -> None:
    for d in regulations.all_documents.values():
        connection.execute(
            "INSERT INTO published.document (id, issuer, family, number, year, citation, title, kind, status, "
            "status_as_of, enacted_on, promulgated_on, effective_on, aliases, published_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (d.id, d.issuer, d.family, d.number, d.year, d.citation, d.title, d.kind, d.status, d.status_as_of,
             d.enacted_on, d.promulgated_on, d.effective_on, list(d.aliases), d.published_at))
    for u in regulations.all_units.values():
        connection.execute(
            "INSERT INTO published.provision_unit (document_id, address, kind, heading_path, wording, text_sha256, "
            "page_start, page_end, valid_from, valid_to, under_review) "
            "VALUES (%s, %s, 'ayat', %s, %s, 'sha', %s, %s, %s, %s, %s)",
            (u.document.id, u.address, list(u.heading_path), u.wording, u.page_start, u.page_end, u.valid_from,
             u.valid_to, u.under_review))
