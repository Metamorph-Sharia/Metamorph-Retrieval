"""The index store in memory: versions, their units, and the embedding cache."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime

from metamorph_market_retrieval.application.ports import IndexVersion
from metamorph_market_retrieval.domain.indexing import IndexUnit


class MemoryStore:
    def __init__(self) -> None:
        self.all_versions: dict[str, IndexVersion] = {}
        self.units: dict[str, list[tuple[IndexUnit, Sequence[float] | None]]] = {}
        self.embeddings: dict[tuple[str, str], list[float]] = {}

    def versions(self) -> list[IndexVersion]:
        return sorted(self.all_versions.values(), key=lambda version: version.built_at)

    def create(self, version: str, model: str | None, built_at: datetime) -> None:
        self.all_versions[version] = IndexVersion(version, model, "building", 0, None, built_at)
        self.units[version] = []

    def cached(self, model: str, hashes: Sequence[str]) -> dict[str, list[float]]:
        return {text_hash: self.embeddings[model, text_hash] for text_hash in hashes
                if (model, text_hash) in self.embeddings}

    def cache(self, model: str, vectors: Mapping[str, Sequence[float]]) -> None:
        self.embeddings |= {(model, text_hash): list(vector) for text_hash, vector in vectors.items()}

    def write(self, version: str, units: Sequence[tuple[IndexUnit, Sequence[float] | None]]) -> None:
        self.units[version].extend(units)

    def finish(self, version: str, source_published_at: datetime | None) -> None:
        self.all_versions[version] = replace(self.all_versions[version], state="ready",
                                             units=len(self.units[version]), source_published_at=source_published_at)

    def activate(self, version: str) -> None:
        for name, known in self.all_versions.items():
            if known.state == "active":
                self.all_versions[name] = replace(known, state="ready")
        self.all_versions[version] = replace(self.all_versions[version], state="active")
