"""The read model is tested twice: in memory, and over PostgreSQL holding the same records.

Set METAMORPH_RETRIEVAL_TEST_DATABASE_URL to a server you may create databases on, e.g. the platform's compose stack:
    METAMORPH_RETRIEVAL_TEST_DATABASE_URL=postgresql://metamorph:metamorph-dev@localhost:5433/postgres uv run pytest
Each session gets a throwaway database, dropped afterwards. Without the variable, the PostgreSQL cases are skipped.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from memory_index import ConceptEmbedder, MemoryIndex
from memory_market import MemoryMarket
from psycopg import sql
from psycopg.types.json import Jsonb

from metamorph_market_retrieval.adapters.index import PostgresIndexStore, PostgresSearchIndex
from metamorph_market_retrieval.adapters.postgres import PostgresMarketReadModel
from metamorph_market_retrieval.application.building import ActivateIndex, BuildIndex
from metamorph_market_retrieval.application.ports import MarketReadModel
from metamorph_market_retrieval.domain.indexing import dataset_unit, passage_unit
from metamorph_market_retrieval.domain.refs import slug

SERVER_URL = os.environ.get("METAMORPH_RETRIEVAL_TEST_DATABASE_URL")
SCHEMA = Path(__file__).with_name("published_market.sql")


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    if not SERVER_URL:
        pytest.skip("METAMORPH_RETRIEVAL_TEST_DATABASE_URL is not set")
    name = f"metamorph_retrieval_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(SERVER_URL, autocommit=True) as server:
        server.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = psycopg.conninfo.make_conninfo(SERVER_URL, dbname=name)
    try:
        with psycopg.connect(url) as connection:
            connection.execute(SCHEMA.read_text(encoding="utf-8"))
            seed(connection, MemoryMarket())
        yield url
    finally:
        with psycopg.connect(SERVER_URL, autocommit=True) as server:
            server.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.database)])
def read_model(request: pytest.FixtureRequest) -> Iterator[MarketReadModel]:
    if request.param == "memory":
        yield MemoryMarket()
        return
    with psycopg.connect(request.getfixturevalue("database_url")) as connection:
        yield PostgresMarketReadModel(connection)


def seed(connection: psycopg.Connection, market: MemoryMarket) -> None:
    """The in-memory read model's records, as the platform would have published them."""
    registers = {company.register.id: company.register for company in market.all_companies}
    for register in registers.values():
        connection.execute(
            "INSERT INTO published_market.register VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (register.id, register.issuer, register.name, list(register.governed_by), register.newest_edition,
             register.editions, register.published_at, list(register.reports)))
    for register_id, edition in market.editions:
        connection.execute("INSERT INTO published_market.edition VALUES (%s, %s, 0, 0, 0)", (register_id, edition))
    for company in market.all_companies:
        connection.execute(
            "INSERT INTO published_market.company VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (company.id, company.register.id, company.legal_name, list(company.names), company.business_type,
             company.status, company.first_listed, company.left_after))
        for number, licence in enumerate(company.licences):
            connection.execute(
                "INSERT INTO published_market.entity VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (_entity_id(company, licence.number), company.id, company.register.id, licence.kind, licence.number,
                 licence.granted_on, company.legal_name, list(company.names), company.business_type,
                 licence.first_listed, licence.last_listed, licence.on_newest_list, licence.left_after,
                 list(company.review_notes) if number == 0 else []))
    for (_, edition), listed in market.editions.items():
        for company, kinds in listed:
            for licence in company.licences:
                if licence.kind in kinds:
                    connection.execute("INSERT INTO published_market.listing VALUES (%s, %s, %s)",
                                       (_entity_id(company, licence.number), edition, company.legal_name))
    for series in market.all_series:
        dataset = series.dataset
        connection.execute(
            "INSERT INTO published_market.dataset VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            (dataset.id, dataset.source, dataset.industry, dataset.group, dataset.metric, dataset.register,
             list(dataset.governed_by), dataset.series_count, dataset.first_period, dataset.last_period,
             dataset.updated, dataset.url, dataset.published_at, dataset.citation, list(dataset.reports)))
        connection.execute(
            "INSERT INTO published_market.series VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (series.id, dataset.id, "measure", series.label, series.first_period, series.last_period,
             series.observations, series.frequency, series.unit))
        for row in market.figures.get(series.id, ()):
            connection.execute("INSERT INTO published_market.observation VALUES (%s, %s, %s, %s)",
                               (series.id, row.period, row.value, row.provisional))
    for industry in market.all_industries:
        connection.execute(
            "INSERT INTO published_market.industry VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (industry.source, industry.name, industry.register, list(industry.governed_by), list(industry.reports),
             list(industry.datasets), industry.published_at))
    for sector in market.all_sectors:
        connection.execute(
            "INSERT INTO published_market.sector VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (sector.id, sector.name, sector.name_en,
             Jsonb([{"source": source, "name": name} for source, name in sector.industries]), list(sector.registers),
             list(sector.governed_by), list(sector.reports), list(sector.datasets), sector.published_at))
    documents = {passage.document.id: passage.document for passage in market.all_passages}
    for document in documents.values():
        if hasattr(document, "family"):
            connection.execute(
                "INSERT INTO published_market.report VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (document.id, document.issuer, document.family, document.edition, document.title,
                 document.published_on, document.language, document.url, document.citation, document.pages,
                 document.passages, document.method, document.published_at))
        else:
            connection.execute(
                "INSERT INTO published_market.release VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (document.id, document.issuer, document.number, document.title, document.published_on,
                 document.language, document.url, document.citation, document.passages, document.published_at))
    for passage in market.all_passages:
        if hasattr(passage.document, "family"):
            connection.execute("INSERT INTO published_market.report_passage VALUES (%s, %s, %s, %s, %s, %s)",
                               (passage.document.id, passage.address, passage.ordinal, passage.page_start,
                                passage.page_end, passage.text))
        else:
            connection.execute("INSERT INTO published_market.release_passage VALUES (%s, %s, %s, %s)",
                               (passage.document.id, passage.address, passage.ordinal, passage.text))
    for mention in market.all_mentions:
        connection.execute("INSERT INTO published_market.mention VALUES (%s, %s, %s, %s, %s)",
                           (mention.kind, mention.document, mention.address, mention.target_kind, mention.target))


def _entity_id(company: object, number: str) -> str:
    return f"{company.register.id}:{slug(number)}"  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def indexed_database(database_url: str) -> Iterator[str]:
    """The throwaway database with retrieval_market: one version by meaning (active) and one by words alone."""
    with psycopg.connect(database_url, autocommit=True) as connection:
        store = PostgresIndexStore(connection)
        store.prepare()
        source = PostgresMarketReadModel(connection)
        built = BuildIndex(source, store, ConceptEmbedder(), now=lambda: datetime(2026, 10, 30, tzinfo=UTC)).run()
        BuildIndex(source, store, None, now=lambda: datetime(2026, 10, 30, 1, tzinfo=UTC)).run()
        ActivateIndex(store).run(built.version)
    yield database_url


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.database)])
def search_index(request: pytest.FixtureRequest) -> Iterator[object]:
    """The active version, by meaning: in memory, and over PostgreSQL."""
    if request.param == "memory":
        market = MemoryMarket()
        units = [*map(passage_unit, market.every_passage()), *map(dataset_unit, market.every_dataset())]
        yield MemoryIndex(units, ConceptEmbedder())
        return
    with psycopg.connect(request.getfixturevalue("indexed_database")) as connection:
        yield PostgresSearchIndex.active(connection)
