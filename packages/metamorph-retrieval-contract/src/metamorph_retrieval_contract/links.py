"""Links between refs: what amends, implements or cites what, and which passages name what.

A provider answers the links it knows about a ref, whether or not it owns the ref: the regulation layer knows what
amends a regulation, the market layer knows which releases name it. The gateway merges them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from metamorph_retrieval_contract.refs import Ref


class LinkType(StrEnum):
    LEGAL_BASIS = "legal_basis"
    IMPLEMENTS = "implements"
    AMENDS = "amends"
    SUPERSEDES = "supersedes"
    REVOKES = "revokes"
    PARTLY_REVOKES = "partly_revokes"
    ADOPTS_FATWA = "adopts_fatwa"
    CHANGES_FATWA = "changes_fatwa"
    REFERS_TO = "refers_to"
    NAMES = "names"  # a report's or a release's passage names it; what the passage did is in its words


class Direction(StrEnum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"
    BOTH = "both"


@dataclass(frozen=True)
class Link:
    type: LinkType
    source: Ref
    target: Ref
    effective_on: date | None = None
    confidence: float | None = None  # how sure the link's resolution is, when it was inferred

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError(f"confidence {self.confidence}: between 0 and 1")
