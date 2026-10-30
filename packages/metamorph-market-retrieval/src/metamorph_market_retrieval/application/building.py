"""Building an index version, and activating one.

A build reads published_market whole, turns each passage, dataset, industry and sector into its index unit, embeds
only the texts whose hash the cache doesn't hold for the model, and writes a new version beside the active one. It
never activates: that waits for the evaluation set to find the new version no worse (`metamorph-eval compare`),
then is one switch.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from metamorph_market_retrieval.application.ports import Embedder, IndexSource, IndexStore
from metamorph_market_retrieval.domain.indexing import (
    IndexUnit,
    dataset_unit,
    industry_unit,
    passage_unit,
    sector_unit,
)
from metamorph_retrieval_contract.errors import InvalidArgument

BATCH = 64  # texts embedded, cached and written at a time, so a stopped build loses at most one batch


@dataclass(frozen=True)
class Built:
    version: str
    units: int
    embedded: int  # texts the model read this time
    cached: int  # texts whose vectors the cache already held


class BuildIndex:
    def __init__(self, source: IndexSource, store: IndexStore, embedder: Embedder | None, *,
                 now: Callable[[], datetime]) -> None:
        self.source = source
        self.store = store
        self.embedder = embedder
        self.now = now

    def run(self) -> Built:
        built_at = self.now()
        version = self._next_version(built_at)
        model = self.embedder.model if self.embedder else None
        self.store.create(version, model, built_at)
        units = [*map(passage_unit, self.source.every_passage()), *map(dataset_unit, self.source.every_dataset()),
                 *map(industry_unit, self.source.industries()), *map(sector_unit, self.source.sectors())]
        embedded = cached = 0
        for start in range(0, len(units), BATCH):
            batch = units[start: start + BATCH]
            vectors, fresh = self._vectors(batch)
            embedded += fresh
            cached += len(batch) - fresh if self.embedder else 0
            self.store.write(version, [(unit, vectors.get(unit.text_hash)) for unit in batch])
        self.store.finish(version, self.source.published_at())
        return Built(version, len(units), embedded, cached)

    def _vectors(self, batch: Sequence[IndexUnit]) -> tuple[dict[str, list[float]], int]:
        """Each unit's vector by text hash, and how many the model read; none without an embedder."""
        if self.embedder is None:
            return {}, 0
        model = self.embedder.model
        vectors = self.store.cached(model, [unit.text_hash for unit in batch])
        missing = list({unit.text_hash: unit for unit in batch if unit.text_hash not in vectors}.values())
        if missing:
            fresh = dict(zip((unit.text_hash for unit in missing),
                             self.embedder.embed_documents([unit.text for unit in missing]), strict=True))
            self.store.cache(model, fresh)
            vectors |= fresh
        return vectors, len(missing)

    def _next_version(self, built_at: datetime) -> str:
        day = f"market-{built_at:%Y-%m-%d}."
        taken = [int(known.version.removeprefix(day)) for known in self.store.versions()
                 if known.version.startswith(day)]
        return f"{day}{max(taken, default=0) + 1}"


class ActivateIndex:
    def __init__(self, store: IndexStore) -> None:
        self.store = store

    def run(self, version: str) -> None:
        known = {existing.version: existing for existing in self.store.versions()}
        if version not in known:
            raise InvalidArgument(f"{version}: no such index version; the versions are {', '.join(known)}")
        if known[version].state not in ("ready", "active"):
            raise InvalidArgument(f"{version} is {known[version].state}; only a finished build can be activated")
        self.store.activate(version)
