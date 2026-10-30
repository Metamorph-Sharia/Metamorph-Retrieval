"""Building the market provider from the environment: the one place that knows which database and index it reads.

    METAMORPH_RETRIEVAL_DATABASE_URL=postgresql://metamorph:…@localhost:5433/metamorph
    METAMORPH_MARKET_INDEX_VERSION=market-2026-10-30.2      optional: a version other than the active one, e.g. a
                                                            candidate the evaluation set is comparing
    METAMORPH_MARKET_MIN_SIMILARITY=0.5                     optional: a similarity floor other than the model's,
                                                            while calibrating one

The session is read only: the provider reads published_market and retrieval_market and can't write anything, there
or elsewhere. Its statements time out before the gateway stops waiting. Without an index version, search is missing
and every other tool still answers.
"""

from __future__ import annotations

import os

import psycopg

from metamorph_market_retrieval.adapters.embedder import MODELS, embedder_for
from metamorph_market_retrieval.adapters.index import PostgresSearchIndex
from metamorph_market_retrieval.adapters.postgres import PostgresMarketReadModel
from metamorph_market_retrieval.adapters.provider import MarketProvider

DATABASE_URL = "METAMORPH_RETRIEVAL_DATABASE_URL"
INDEX_VERSION = "METAMORPH_MARKET_INDEX_VERSION"
MIN_SIMILARITY = "METAMORPH_MARKET_MIN_SIMILARITY"
STATEMENT_TIMEOUT_MS = 8_000  # under the gateway's budget, so a late query ends rather than holding the session


def market_provider() -> MarketProvider:
    options = f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS}"
    connection = psycopg.connect(database_url(), autocommit=True, options=options)
    pinned = os.environ.get(INDEX_VERSION)
    index = PostgresSearchIndex.at(connection, pinned) if pinned else PostgresSearchIndex.active(connection)
    if index is None or index.model is None:
        return MarketProvider(PostgresMarketReadModel(connection), index=index)
    return MarketProvider(PostgresMarketReadModel(connection), index=index, embedder=embedder_for(index.model),
                          min_similarity=float(os.environ.get(MIN_SIMILARITY, MODELS[index.model].min_similarity)))


def database_url() -> str:
    url = os.environ.get(DATABASE_URL)
    if not url:
        raise ValueError(f"set {DATABASE_URL} to the database holding published_market")
    return url
