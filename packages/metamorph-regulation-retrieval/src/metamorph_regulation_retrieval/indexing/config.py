"""Where the builder reads and writes, and what it refuses to include.

Two connections: the platform's `published` schema (read only) and the index
database (read/write). They are usually the same database, and the same URL works
for both; keeping them separate lets a deployment point at a replica for reads.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime

INDEX_URL = "METAMORPH_REGULATION_INDEX_URL"
RETRIEVAL_URL = "METAMORPH_RETRIEVAL_DATABASE_URL"
PUBLISHED_URL = "METAMORPH_REGULATION_PUBLISHED_URL"
EXCLUDED = "METAMORPH_REGULATION_EXCLUDED"
SNAPSHOT = "METAMORPH_REGULATION_SNAPSHOT"

# Documents not to index, comma separated. None by default: every published document is searchable. UU 27/2022
# (personal data protection) was left out until 2026-11-03, when the owner decided to index it.
DEFAULT_EXCLUDED = ""

SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def index_url() -> str:
    """The index database: METAMORPH_REGULATION_INDEX_URL, or the retrieval layer's own database, as the provider's
    wiring finds it. PGOPTIONS can name the schema it is in."""
    value = (os.environ.get(INDEX_URL, "") or os.environ.get(RETRIEVAL_URL, "")).strip()
    if not value:
        raise ValueError(f"set {INDEX_URL} (or {RETRIEVAL_URL}) to the index database")
    return value


def published_url() -> str:
    return os.environ.get(PUBLISHED_URL, "").strip() or index_url()


def excluded_documents() -> list[str]:
    raw = os.environ.get(EXCLUDED, DEFAULT_EXCLUDED)
    return [item.strip() for item in raw.split(",") if item.strip()]


def snapshot_id() -> str:
    return os.environ.get(SNAPSHOT, "").strip() or datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")


def table_name(value: str) -> str:
    """Table names come from the command line, so they are checked before they reach SQL."""
    if not SAFE_NAME.fullmatch(value):
        raise ValueError(f"{value!r} is not a table name")
    return value


def tag(snapshot: str) -> str:
    """The suffix that names this snapshot's tables: the last 12 alphanumerics."""
    cleaned = "".join(character for character in snapshot if character.isalnum())
    return cleaned[-12:] or "index"
