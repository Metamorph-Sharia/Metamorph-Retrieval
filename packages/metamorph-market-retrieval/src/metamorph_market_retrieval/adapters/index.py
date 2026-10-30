"""The index in PostgreSQL: the `retrieval_market` schema, beside the published_market it is built from.

    index_version     one row a build: its model, its state (building, ready, active: one at a time), its source
    unit              each version's units: ref, filters, full text (Indonesian) and the vector (pgvector)
    embedding_cache   vectors by text hash and model, kept across versions, so a rebuild embeds only new text

The store writes (the build's session); the search index only reads (the provider's read-only session). About 7,000
units a version, so vectors are searched exactly, without an approximate index.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from metamorph_market_retrieval.application.ports import WORDS_SHARE, IndexVersion, Match, UnitFilter
from metamorph_market_retrieval.domain.indexing import IndexUnit
from metamorph_retrieval_contract.refs import Ref

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS retrieval_market;
CREATE TABLE IF NOT EXISTS retrieval_market.index_version (
    version text PRIMARY KEY,
    model text,
    state text NOT NULL CHECK (state IN ('building', 'ready', 'active')),
    units integer NOT NULL DEFAULT 0,
    source_published_at timestamptz,
    built_at timestamptz NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS index_version_one_active ON retrieval_market.index_version (state)
    WHERE state = 'active';
CREATE TABLE IF NOT EXISTS retrieval_market.unit (
    version text NOT NULL REFERENCES retrieval_market.index_version ON DELETE CASCADE,
    ref text NOT NULL,
    kind text NOT NULL,
    document text,
    issuer text,
    published_on date,
    text_hash text NOT NULL,
    words tsvector NOT NULL,
    embedding vector,
    PRIMARY KEY (version, ref)
);
CREATE INDEX IF NOT EXISTS unit_words ON retrieval_market.unit USING gin (words);
CREATE TABLE IF NOT EXISTS retrieval_market.embedding_cache (
    model text NOT NULL,
    text_hash text NOT NULL,
    embedding vector NOT NULL,
    PRIMARY KEY (model, text_hash)
);
"""
LANGUAGE = "indonesian"  # the passages' language; its stemmer joins pembiayaan and dibiayai
BY_LENGTH = 1  # ts_rank's normalisation: rank / (1 + log(length)), so a long passage doesn't win on length alone
FILTER = """
    AND kind = ANY(%(kinds)s)
    AND (cardinality(%(documents)s::text[]) = 0 OR document = ANY(%(documents)s))
    AND (cardinality(%(issuers)s::text[]) = 0 OR lower(issuer) = ANY(%(issuers)s))
    AND (%(published_from)s::date IS NULL OR published_on >= %(published_from)s)
    AND (%(published_to)s::date IS NULL OR published_on <= %(published_to)s)"""
VERSIONS = "SELECT * FROM retrieval_market.index_version"


class PostgresIndexStore:
    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def prepare(self) -> None:
        """The schema, if it isn't there yet. Needs a session that may create an extension and a schema."""
        self.connection.execute(SCHEMA)

    def versions(self) -> list[IndexVersion]:
        return [_version(row) for row in _rows(self.connection, f"{VERSIONS} ORDER BY built_at, version", {})]

    def create(self, version: str, model: str | None, built_at: datetime) -> None:
        self.connection.execute("INSERT INTO retrieval_market.index_version (version, model, state, built_at) "
                                "VALUES (%s, %s, 'building', %s)", (version, model, built_at))

    def cached(self, model: str, hashes: Sequence[str]) -> dict[str, list[float]]:
        rows = _rows(self.connection, "SELECT text_hash, embedding::text AS embedding FROM retrieval_market."
                     "embedding_cache WHERE model = %(model)s AND text_hash = ANY(%(hashes)s)",
                     {"model": model, "hashes": list(hashes)})
        return {row["text_hash"]: _floats(row["embedding"]) for row in rows}

    def cache(self, model: str, vectors: Mapping[str, Sequence[float]]) -> None:
        with self.connection.cursor() as cursor:
            cursor.executemany("INSERT INTO retrieval_market.embedding_cache VALUES (%s, %s, %s::vector) "
                               "ON CONFLICT DO NOTHING",
                               [(model, text_hash, _vector(vector)) for text_hash, vector in vectors.items()])

    def write(self, version: str, units: Sequence[tuple[IndexUnit, Sequence[float] | None]]) -> None:
        with self.connection.cursor() as cursor:
            cursor.executemany(
                f"INSERT INTO retrieval_market.unit VALUES (%s, %s, %s, %s, %s, %s, %s, "
                f"to_tsvector('{LANGUAGE}', %s), %s::vector)",
                [(version, str(unit.ref), unit.kind, str(unit.document) if unit.document else None, unit.issuer,
                  unit.published_on, unit.text_hash, unit.text, _vector(vector) if vector else None)
                 for unit, vector in units])

    def finish(self, version: str, source_published_at: datetime | None) -> None:
        self.connection.execute(
            "UPDATE retrieval_market.index_version SET state = 'ready', source_published_at = %s, "
            "units = (SELECT count(*) FROM retrieval_market.unit WHERE version = %s) WHERE version = %s",
            (source_published_at, version, version))

    def activate(self, version: str) -> None:
        with self.connection.transaction():
            self.connection.execute("UPDATE retrieval_market.index_version SET state = 'ready' WHERE state = 'active'")
            self.connection.execute("UPDATE retrieval_market.index_version SET state = 'active' WHERE version = %s",
                                    (version,))


class PostgresSearchIndex:
    def __init__(self, connection: psycopg.Connection, version: IndexVersion) -> None:
        self.connection = connection
        self.version = version.version
        self.model = version.model

    @classmethod
    def active(cls, connection: psycopg.Connection) -> PostgresSearchIndex | None:
        """The active version; None when there is none, or no index at all yet."""
        exists = connection.execute("SELECT to_regclass('retrieval_market.index_version')").fetchone()[0]
        rows = _rows(connection, f"{VERSIONS} WHERE state = 'active'", {}) if exists else []
        return cls(connection, _version(rows[0])) if rows else None

    @classmethod
    def at(cls, connection: psycopg.Connection, version: str) -> PostgresSearchIndex:
        rows = _rows(connection, f"{VERSIONS} WHERE version = %(version)s AND state <> 'building'",
                     {"version": version})
        if not rows:
            raise ValueError(f"{version}: no finished index version by that name")
        return cls(connection, _version(rows[0]))

    def by_words(self, query: str, where: UnitFilter, limit: int) -> list[Match]:
        # Some of the question's words, not all: a question is longer than what answers it. But at least a share of
        # them, so one common word isn't a match. The stems are joined by OR and read back with 'simple', which
        # keeps them as they are; the share counts the stems a unit holds.
        return self._matches(f"""
            WITH asked AS (SELECT tsvector_to_array(to_tsvector('{LANGUAGE}', %(query)s)) AS stems)
            SELECT ref, ts_rank(words, query, {BY_LENGTH}) AS score, published_on
            FROM retrieval_market.unit, asked,
                 to_tsquery('simple', replace(plainto_tsquery('{LANGUAGE}', %(query)s)::text, ' & ', ' | ')) AS query
            WHERE version = %(version)s AND words @@ query {FILTER}
              AND cardinality(ARRAY(SELECT unnest(tsvector_to_array(words)) INTERSECT SELECT unnest(asked.stems)))
                  >= %(share)s * cardinality(asked.stems)
            ORDER BY score DESC, ref LIMIT %(limit)s""", where, limit, query=query, share=WORDS_SHARE)

    def by_meaning(self, vector: Sequence[float], where: UnitFilter, limit: int) -> list[Match]:
        if self.model is None:
            return []
        return self._matches(f"""
            SELECT ref, 1 - (embedding <=> %(vector)s::vector) AS score, published_on
            FROM retrieval_market.unit
            WHERE version = %(version)s AND embedding IS NOT NULL {FILTER}
            ORDER BY embedding <=> %(vector)s::vector, ref LIMIT %(limit)s""", where, limit, vector=_vector(vector))

    def _matches(self, statement: str, where: UnitFilter, limit: int, **parameters: Any) -> list[Match]:
        rows = _rows(self.connection, statement, {
            "version": self.version, "limit": limit, "kinds": sorted(where.kinds),
            "documents": sorted(str(ref) for ref in where.documents), "issuers": sorted(where.issuers),
            "published_from": where.published_from, "published_to": where.published_to, **parameters})
        return [Match(Ref.parse(row["ref"]), float(row["score"]), row["published_on"]) for row in rows]


def _rows(connection: psycopg.Connection, query: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, parameters).fetchall()  # type: ignore[arg-type]


def _version(row: dict[str, Any]) -> IndexVersion:
    return IndexVersion(row["version"], row["model"], row["state"], row["units"], row["source_published_at"],
                        row["built_at"])


def _vector(values: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(value)) for value in values) + "]"


def _floats(text: str) -> list[float]:
    return [float(value) for value in text.strip("[]").split(",")]
