"""What the stand-in reads from published: documents, and the provisions the read contract says to cite."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Document:
    id: str  # ojk:pojk:2024:40
    issuer: str
    family: str
    number: str
    year: int
    citation: str
    title: str
    kind: str  # law, regulation, implementing_rule, fatwa…
    status: str  # in_force, amended, partly_revoked, revoked, not_yet_in_force, unknown
    status_as_of: date | None
    enacted_on: date | None
    promulgated_on: date | None
    effective_on: date | None
    aliases: tuple[str, ...]
    published_at: datetime


@dataclass(frozen=True)
class Unit:
    """A provision_unit: the smallest provision with wording of its own, e.g. pasal-5/ayat-1."""

    document: Document
    address: str
    heading_path: tuple[str, ...]
    wording: str
    page_start: int | None
    page_end: int | None
    valid_from: date | None
    valid_to: date | None
    under_review: bool  # a review note names it, or a provision holding it
