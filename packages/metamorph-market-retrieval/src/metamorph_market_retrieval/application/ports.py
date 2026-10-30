"""What the use cases need from published_market. One adapter implements it over PostgreSQL; tests, in memory.

Every method reads; none writes. Lists come in the read contract's order unless a method says otherwise.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from metamorph_market_retrieval.domain.indexing import IndexUnit
from metamorph_market_retrieval.domain.records import (
    Announcement,
    Company,
    Dataset,
    Industry,
    Listed,
    Mention,
    ObservationRow,
    Passage,
    Register,
    Release,
    Report,
    Sector,
    Series,
)
from metamorph_retrieval_contract.refs import Ref


class MarketReadModel(Protocol):
    def published_at(self) -> datetime | None:
        """When published_market was last published, whole or links-only: how fresh every answer is."""
        ...

    def companies(self, register: str | None, status: str | None, business_type: str | None) -> list[Company]: ...

    def listed_on(self, register: str | None, day: date) -> list[Listed]:
        """The companies on each register's edition current on `day`: its newest edition on or before it."""
        ...

    def announcements(self, company_ids: Sequence[str]) -> Mapping[str, Sequence[Announcement]]:
        """The release passages naming each company, newest first."""
        ...

    def company(self, company_id: str) -> Company | None: ...

    def register(self, register_id: str) -> Register | None: ...

    def industries(self) -> list[Industry]: ...

    def sectors(self) -> list[Sector]: ...

    def dataset(self, dataset_id: str) -> Dataset | None: ...

    def datasets_matching(self, words: Sequence[str], source: str | None, limit: int) -> list[tuple[Dataset, float]]:
        """Datasets whose metric, group or industry holds the words, best first, with their scores; between equals,
        the one whose figures run latest, so a retired table gives way to its successor."""
        ...

    def series(self, series_ids: Sequence[str]) -> list[Series]: ...

    def series_matching(
        self, dataset_ids: Sequence[str], words: Sequence[str], frequency: str | None, limit: int
    ) -> list[tuple[Series, float]]:
        """Up to `limit` series of each dataset, those whose labels hold the most of the words first, with their
        scores. A series whose label holds none still comes, after them: its dataset may carry the meaning."""
        ...

    def observations(self, series_ids: Sequence[str], start: date | None, end: date | None) -> Mapping[
        str, Sequence[ObservationRow]
    ]:
        """Each series' figures whose period starts between `start` and `end`, oldest first."""
        ...

    def report(self, report_id: str) -> Report | None: ...

    def release(self, release_id: str) -> Release | None: ...

    def passages(self, kind: str, document_id: str, address: str, window: int) -> list[Passage]:
        """The passage and up to `window` passages either side, in reading order; empty when there is no such one."""
        ...

    def mentions_of(self, target_kind: str, target: str) -> list[Mention]:
        """The passages naming a regulation or a company, newest document first."""
        ...

    def mentions_in(self, kind: str, document_id: str, address: str | None) -> list[Mention]:
        """What a document names, or one of its passages, in reading order."""
        ...


@dataclass(frozen=True)
class UnitFilter:
    """Which index units a search may return: explicit, and never relaxed behind the caller's back."""

    kinds: frozenset[str]
    issuers: frozenset[str] = frozenset()  # case folded
    documents: frozenset[Ref] = frozenset()  # whole reports and releases
    published_from: date | None = None
    published_to: date | None = None

    def keeps(self, unit: IndexUnit) -> bool:
        published = unit.published_on
        return (unit.kind in self.kinds
                and (not self.documents or unit.document in self.documents)
                and (not self.issuers or (unit.issuer or "").casefold() in self.issuers)
                and (self.published_from is None or (published is not None and published >= self.published_from))
                and (self.published_to is None or (published is not None and published <= self.published_to)))


@dataclass(frozen=True)
class Match:
    ref: Ref
    score: float  # by words, a full-text rank; by meaning, the cosine similarity
    published_on: date | None


WORDS_SHARE = 0.5  # a match by words holds at least this share of the question's words, not just any one of them


class SearchIndex(Protocol):
    """One version of the index: units found by words or by meaning, within a filter, best first.

    By words: units holding at least WORDS_SHARE of the question's words (as stems), so a question nothing speaks to
    doesn't match on one common word. By meaning: the nearest, with their cosine similarity."""

    version: str
    model: str | None  # the embedding model its vectors come from; None when it holds none

    def by_words(self, query: str, where: UnitFilter, limit: int) -> list[Match]: ...

    def by_meaning(self, vector: Sequence[float], where: UnitFilter, limit: int) -> list[Match]: ...


class Embedder(Protocol):
    model: str

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


class IndexSource(Protocol):
    """What an index is built from: published_market's passages, datasets, industries and sectors, whole."""

    def published_at(self) -> datetime | None: ...

    def every_passage(self) -> list[Passage]: ...

    def every_dataset(self) -> list[Dataset]: ...

    def industries(self) -> list[Industry]: ...

    def sectors(self) -> list[Sector]: ...


@dataclass(frozen=True)
class IndexVersion:
    version: str  # market-2026-10-30.1
    model: str | None  # None: full text only
    state: str  # building, ready, active (one at a time)
    units: int
    source_published_at: datetime | None  # the publish it was built from
    built_at: datetime


class IndexStore(Protocol):
    """Where index versions are written. Versions are built beside the active one and activated by one switch."""

    def versions(self) -> list[IndexVersion]:
        """Oldest first."""
        ...

    def create(self, version: str, model: str | None, built_at: datetime) -> None: ...

    def cached(self, model: str, hashes: Sequence[str]) -> dict[str, list[float]]: ...

    def cache(self, model: str, vectors: Mapping[str, Sequence[float]]) -> None: ...

    def write(self, version: str, units: Sequence[tuple[IndexUnit, Sequence[float] | None]]) -> None: ...

    def finish(self, version: str, source_published_at: datetime | None) -> None:
        """Ready: whole, and not yet active."""
        ...

    def activate(self, version: str) -> None:
        """The one active version from now on; the previous one stays, ready, for rollback."""
        ...
