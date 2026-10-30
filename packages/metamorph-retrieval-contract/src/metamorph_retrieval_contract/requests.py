"""What a caller asks a provider. Checked when built, so a provider can trust every request it is given.

Filters are explicit and never relaxed behind the caller's back: widening a search is the agent's decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from metamorph_retrieval_contract.errors import InvalidArgument
from metamorph_retrieval_contract.evidence import LegalForce
from metamorph_retrieval_contract.links import Direction, LinkType
from metamorph_retrieval_contract.refs import Ref

DEFAULT_LIMIT = 8
MAX_LIMIT = 25  # one call never floods the agent's context


class Sort(StrEnum):
    RELEVANCE = "relevance"
    NEWEST = "newest"


@dataclass(frozen=True)
class SearchRequest:
    query: str
    kinds: frozenset[str] = frozenset()  # empty: every kind the provider holds
    issuers: frozenset[str] = frozenset()
    documents: tuple[Ref, ...] = ()  # search only within these, e.g. the regulations industry_context named
    published_from: date | None = None
    published_to: date | None = None
    in_force_on: date | None = None
    legal_force: frozenset[LegalForce] = frozenset()
    sort: Sort = Sort.RELEVANCE
    limit: int = DEFAULT_LIMIT
    cursor: str | None = None

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise InvalidArgument("query: say what to search for")
        check_limit(self.limit)
        if self.published_from and self.published_to and self.published_from > self.published_to:
            raise InvalidArgument(f"published_from {self.published_from} is after published_to {self.published_to}")
        parts = [str(ref) for ref in self.documents if ref.address is not None]
        if parts:
            raise InvalidArgument(f"documents: {', '.join(parts)} is a part, not a whole document")


@dataclass(frozen=True)
class LinksRequest:
    direction: Direction = Direction.BOTH
    types: frozenset[LinkType] = frozenset()  # empty: every type
    limit: int = DEFAULT_LIMIT
    cursor: str | None = None

    def __post_init__(self) -> None:
        check_limit(self.limit)


def check_limit(limit: int) -> None:
    if limit < 1:
        raise InvalidArgument(f"limit {limit}: ask for at least 1")
    if limit > MAX_LIMIT:
        raise InvalidArgument(f"limit {limit}: at most {MAX_LIMIT}")
