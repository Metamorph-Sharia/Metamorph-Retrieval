"""Building an index version from published_market, and activating it."""

from datetime import UTC, datetime

import pytest
from market_samples import PUBLISHED_AT
from memory_index import ConceptEmbedder
from memory_market import MemoryMarket
from memory_store import MemoryStore

from metamorph_market_retrieval.application.building import ActivateIndex, BuildIndex
from metamorph_retrieval_contract.errors import InvalidArgument

ON = datetime(2026, 10, 30, 8, 0, tzinfo=UTC)


class Counting(ConceptEmbedder):
    def __init__(self) -> None:
        self.embedded: list[str] = []

    def embed_documents(self, texts):  # noqa: ANN001, ANN201
        self.embedded.extend(texts)
        return super().embed_documents(texts)


def build(store: MemoryStore, embedder: ConceptEmbedder | None = None, market: MemoryMarket | None = None):  # noqa: ANN201
    return BuildIndex(market or MemoryMarket(), store, embedder, now=lambda: ON).run()


def test_a_build_indexes_every_passage_and_dataset_card_at_a_new_version() -> None:
    store, market = MemoryStore(), MemoryMarket()

    built = build(store, ConceptEmbedder(), market)

    assert built.version == "market-2026-10-30.1"
    kinds = sorted({unit.kind for unit, _ in store.units[built.version]})
    assert kinds == ["dataset", "industry", "release", "report", "sector"]
    assert built.units == (len(market.all_passages) + len({series.dataset.id for series in market.all_series})
                           + len(market.industries()) + len(market.sectors()))
    assert all(vector is not None for _, vector in store.units[built.version])
    version = store.all_versions[built.version]
    assert (version.state, version.model, version.source_published_at) == ("ready", "concepts-64", PUBLISHED_AT)


def test_a_build_without_an_embedder_is_full_text_only() -> None:
    store = MemoryStore()

    built = build(store)

    assert store.all_versions[built.version].model is None
    assert all(vector is None for _, vector in store.units[built.version])


def test_unchanged_texts_are_never_embedded_twice() -> None:
    store, embedder = MemoryStore(), Counting()

    first = build(store, embedder)
    embedded_once = len(embedder.embedded)
    second = build(store, embedder)

    assert (first.embedded, second.embedded, second.cached) == (embedded_once, 0, embedded_once)
    assert second.version == "market-2026-10-30.2"


def test_a_build_doesnt_activate_and_activating_keeps_the_previous_version_for_rollback() -> None:
    store = MemoryStore()
    first, second = build(store), build(store)

    ActivateIndex(store).run(first.version)
    ActivateIndex(store).run(second.version)

    assert [(version.version, version.state) for version in store.versions()] == [
        ("market-2026-10-30.1", "ready"), ("market-2026-10-30.2", "active")]


def test_only_a_ready_version_can_be_activated() -> None:
    with pytest.raises(InvalidArgument, match="market-2099-01-01.1: no such index version; the versions are "
                                              "market-2026-10-30.1"):
        store = MemoryStore()
        build(store)
        ActivateIndex(store).run("market-2099-01-01.1")
