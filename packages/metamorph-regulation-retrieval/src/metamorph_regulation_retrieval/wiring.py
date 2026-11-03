"""Building the provider from the environment: where the regulation retrieval service answers.

    METAMORPH_REGULATION_RETRIEVAL_URL=http://rag-service:8080
    METAMORPH_REGULATION_RETRIEVAL_TOKEN=…       when the service enforces one
"""

from __future__ import annotations

import os

from metamorph_regulation_retrieval.adapters.provider import RegulationProvider

URL = "METAMORPH_REGULATION_RETRIEVAL_URL"
TOKEN = "METAMORPH_REGULATION_RETRIEVAL_TOKEN"
TIMEOUT = "METAMORPH_REGULATION_RETRIEVAL_TIMEOUT"


def regulation_provider() -> RegulationProvider:
    url = os.environ.get(URL)
    if not url:
        raise ValueError(f"set {URL} to the regulation retrieval service, such as http://rag-service:8080")
    return RegulationProvider(
        url,
        token=os.environ.get(TOKEN) or None,
        timeout=float(os.environ.get(TIMEOUT, "10")),
    )
