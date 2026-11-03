"""Building the provider from the environment.

    METAMORPH_REGULATION_INDEX_URL      the database holding the index
                                        (falls back to METAMORPH_DATABASE_URL, as Airflow has it)
    METAMORPH_REGULATION_CHUNK_TABLE    (default regulation_chunk_live)
    METAMORPH_REGULATION_EMBED_TABLE    (default regulation_emb_live)
    METAMORPH_REGULATION_META_TABLE     (default regulation_meta_live)
    METAMORPH_REGULATION_INDEX_VERSION  what provenance reports (default regulation-index)
"""

from __future__ import annotations

import os

from metamorph_regulation_retrieval.adapters.provider import RegulationProvider
from metamorph_regulation_retrieval.embedder import SentenceTransformerEmbedder
from metamorph_regulation_retrieval.store import PostgresStore

INDEX_URL = "METAMORPH_REGULATION_INDEX_URL"
DATABASE_URL = "METAMORPH_DATABASE_URL"


def regulation_provider() -> RegulationProvider:
    url = os.environ.get(INDEX_URL) or os.environ.get(DATABASE_URL)
    if not url:
        raise ValueError(f"set {INDEX_URL} to the database holding the regulation index")
    return RegulationProvider(PostgresStore(url), SentenceTransformerEmbedder())
