"""An index in memory, and an embedder whose "meaning" is a few concepts shared by English and Indonesian words:
enough to test what full text can't find and meaning can, without a model."""

from __future__ import annotations

import math
import re
import zlib
from collections.abc import Sequence

from metamorph_market_retrieval.application.ports import WORDS_SHARE, Match, UnitFilter
from metamorph_market_retrieval.domain.indexing import IndexUnit

DIMENSIONS = 64
CONCEPTS = {"sharia": "syariah", "financing": "pembiayaan", "productive": "produktif", "sector": "sektor",
            "revoked": "mencabut", "revokes": "mencabut", "licence": "izin", "business": "usaha", "msme": "umkm",
            "money": "uang", "supply": "beredar", "lending": "pendanaan"}
WORD = re.compile(r"\w+")


def words(text: str) -> list[str]:
    return WORD.findall(text.casefold())


class ConceptEmbedder:
    model = "concepts-64"

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * DIMENSIONS
        for word in words(text):
            vector[zlib.crc32(CONCEPTS.get(word, word).encode()) % DIMENSIONS] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class MemoryIndex:
    def __init__(self, units: Sequence[IndexUnit], embedder: ConceptEmbedder | None = None,
                 version: str = "market-test.1") -> None:
        self.units = list(units)
        self.version = version
        self.model = embedder.model if embedder else None
        self.vectors = dict(zip((unit.ref for unit in units), embedder.embed_documents([unit.text for unit in units]),
                                strict=True)) if embedder else {}

    def by_words(self, query: str, where: UnitFilter, limit: int) -> list[Match]:
        asked = set(words(query))
        scored = [(len(asked & set(words(unit.text))), unit) for unit in self.units if where.keeps(unit)]
        return _best([(float(score), unit) for score, unit in scored if score and score >= WORDS_SHARE * len(asked)],
                     limit)

    def by_meaning(self, vector: Sequence[float], where: UnitFilter, limit: int) -> list[Match]:
        scored = [(sum(a * b for a, b in zip(vector, self.vectors[unit.ref], strict=True)), unit)
                  for unit in self.units if where.keeps(unit) and unit.ref in self.vectors]
        return _best(scored, limit)


def _best(scored: list[tuple[float, IndexUnit]], limit: int) -> list[Match]:
    ranked = sorted(scored, key=lambda pair: (-pair[0], str(pair[1].ref)))[:limit]
    return [Match(unit.ref, score, unit.published_on) for score, unit in ranked]
