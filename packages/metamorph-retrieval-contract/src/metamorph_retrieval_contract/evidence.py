"""Evidence: what every provider returns, whatever it holds. The envelope is shared; only the body differs.

Evidence is never an answer. It says what a source says, how to cite it, and how much it counts: its legal force,
and what qualifies it (a status, a validity, a provisional mark, an as-of date). An agent that reads only these
fields still tells a binding rule from a roadmap.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar

from metamorph_retrieval_contract.refs import Ref


class LegalForce(StrEnum):
    BINDING = "binding"  # laws, regulations, implementing rules
    SHARIA = "sharia"  # DSN-MUI fatwas, guidelines and circulars
    EXPLANATORY = "explanatory"  # how an issuer explains a rule; never the rule
    NONE = "none"  # reports, releases, statistics, companies: what a regulator reports, announces or counts


class MatchedBy(StrEnum):
    SEMANTIC = "semantic"
    WORDS = "words"


class EmptyReason(StrEnum):
    NO_MATCH = "no_match"  # rephrase
    FILTERS_EXCLUDE_ALL = "filters_exclude_all"  # widen the filters


@dataclass(frozen=True)
class Qualifiers:
    """What limits how much the evidence counts. A field that doesn't apply to a kind stays at its default."""

    status: str | None = None  # documents: in_force, revoked…; companies: licensed, registered, left
    valid_from: date | None = None
    valid_to: date | None = None
    under_review: bool = False  # the parser noted a gap in the document's numbering
    provisional: bool = False  # the source marks a figure so
    as_of: date | None = None  # when the source last stood behind it


@dataclass(frozen=True)
class Provenance:
    provider: str
    index_version: str  # the build of the provider's index that answered
    source_published_at: datetime  # the platform's publish the evidence comes from


@dataclass(frozen=True)
class PageSpan:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(f"page {self.start} to {self.end} runs backwards")


@dataclass(frozen=True)
class Text:
    wording: str
    pages: PageSpan | None = None  # a release has no pages


@dataclass(frozen=True)
class Observation:
    period: str  # 2026-08, 2026-Q2, 2026-S1, 2025
    value: float  # as the source gives it, never rescaled
    provisional: bool = False


@dataclass(frozen=True)
class Figures:
    unit: str | None  # as the source states it, or None when it doesn't
    frequency: str  # monthly, quarterly, semiannual, annual
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class Record:
    """A record's fields, as JSON values: a company's standing, a dataset's links."""

    fields: Mapping[str, Any]


Body = Text | Figures | Record


@dataclass(frozen=True)
class Evidence:
    ref: Ref
    kind: str  # regulation, fatwa, report, release, dataset, series, company…
    citation: str  # quote it as is
    title: str
    legal_force: LegalForce
    qualifiers: Qualifiers
    published_on: date | None
    url: str | None
    body: Body | None  # None in a card
    provenance: Provenance

    def card(self) -> Evidence:
        """The evidence without its body: what `describe` returns, cheaply and in batches."""
        return replace(self, body=None)


@dataclass(frozen=True)
class Hit:
    evidence: Evidence
    rank: int  # from 1
    score: float  # comparable only within one provider and one call
    matched_by: frozenset[MatchedBy]

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError(f"rank {self.rank}: hits are ranked from 1")
        if not self.matched_by:
            raise ValueError("matched_by: a hit says how it matched")


Item = TypeVar("Item")


@dataclass(frozen=True)
class Page(Generic[Item]):
    items: tuple[Item, ...]
    cursor: str | None = None  # pass it back for the next page; None when there is none
    empty_reason: EmptyReason | None = None
    warnings: tuple[str, ...] = field(default=())  # what a provider couldn't do, e.g. a filter it doesn't apply

    def __post_init__(self) -> None:
        if not self.items and self.empty_reason is None:
            raise ValueError("an empty page says why it is empty")
        if self.items and self.empty_reason is not None:
            raise ValueError("only an empty page has an empty_reason")

    @classmethod
    def empty(cls, reason: EmptyReason, warnings: tuple[str, ...] = ()) -> Page[Item]:
        return cls(items=(), empty_reason=reason, warnings=warnings)
