"""Building the gateway from the environment: the one place that knows which providers are joined.

    METAMORPH_RETRIEVAL_PROVIDERS   module:function factories, comma separated (default: the market provider and the
                                    regulation stand-in, each reading METAMORPH_RETRIEVAL_DATABASE_URL)
    METAMORPH_RETRIEVAL_TIMEOUT     seconds a provider has to answer one call (default 10)
    METAMORPH_RETRIEVAL_CALL_LOG    the call log's directory (default var/call-log)

Providers are named, not imported, so the gateway depends on no provider: Friend 2's joins by adding its factory.
"""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from pathlib import Path

from metamorph_retrieval_contract.provider import RetrievalProvider
from metamorph_retrieval_gateway.adapters.call_log import JsonLinesCallLog
from metamorph_retrieval_gateway.adapters.tracing import SpanCallLog
from metamorph_retrieval_gateway.application.calls import AllCallLogs
from metamorph_retrieval_gateway.application.catalog import Catalog
from metamorph_retrieval_gateway.application.gateway import TIMEOUT, Gateway

PROVIDERS = "METAMORPH_RETRIEVAL_PROVIDERS"
TIMEOUT_SECONDS = "METAMORPH_RETRIEVAL_TIMEOUT"
CALL_LOG = "METAMORPH_RETRIEVAL_CALL_LOG"
DEFAULT_PROVIDERS = ("metamorph_market_retrieval.wiring:market_provider,"
                     "metamorph_regulation_standin.wiring:standin_provider")
DEFAULT_CALL_LOG = "var/call-log"
EXAMPLE = "metamorph_market_retrieval.wiring:market_provider"


def catalog_from(environment: Mapping[str, str]) -> Catalog:
    gateway = Gateway(providers_from(environment.get(PROVIDERS, DEFAULT_PROVIDERS)),
                      timeout=float(environment.get(TIMEOUT_SECONDS, TIMEOUT)))
    calls = AllCallLogs([JsonLinesCallLog(Path(environment.get(CALL_LOG, DEFAULT_CALL_LOG))), SpanCallLog()])
    return Catalog(gateway, calls=calls)


def providers_from(named: str) -> list[RetrievalProvider]:
    factories = [name.strip() for name in named.split(",") if name.strip()]
    if not factories:
        raise ValueError("name at least one provider, as module:function")
    return [_factory(name)() for name in factories]


def _factory(name: str):  # noqa: ANN202 - a function building a provider
    module_name, _, attribute = name.partition(":")
    if not attribute:
        raise ValueError(f"{name}: name a factory as module:function, e.g. {EXAMPLE}")
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        raise ValueError(f"{name}: no module named {module_name}") from None
    if not hasattr(module, attribute):
        raise ValueError(f"{name}: {module_name} has no {attribute}")
    factory = getattr(module, attribute)
    if not callable(factory):
        raise ValueError(f"{name}: not a function")
    return factory
