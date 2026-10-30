"""Building the stand-in from the environment: the database holding published, read in a read-only session.

    METAMORPH_RETRIEVAL_DATABASE_URL=postgresql://metamorph:…@localhost:5433/metamorph
"""

from __future__ import annotations

import os

import psycopg

from metamorph_regulation_standin.adapters.postgres import PostgresRegulationReadModel
from metamorph_regulation_standin.adapters.provider import StandinProvider

DATABASE_URL = "METAMORPH_RETRIEVAL_DATABASE_URL"
STATEMENT_TIMEOUT_MS = 8_000  # under the gateway's budget, so a late query ends rather than holding the session


def standin_provider() -> StandinProvider:
    url = os.environ.get(DATABASE_URL)
    if not url:
        raise ValueError(f"set {DATABASE_URL} to the database holding published")
    options = f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS}"
    return StandinProvider(PostgresRegulationReadModel(psycopg.connect(url, autocommit=True, options=options)))
