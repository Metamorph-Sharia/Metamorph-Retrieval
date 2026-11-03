"""One retrieved passage, with everything a citation needs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Passage:
    chunk_id: str
    document_id: str
    address: str
    title: str
    citation: str
    text: str
    doc_kind: str | None = None
    doc_status: str | None = None
    valid_from: object = None
    valid_to: object = None
    effective_on: object = None
    promulgated_on: object = None
    published_at: object = None
    issuer: str | None = None
    family: str | None = None
    number: str | None = None
    year: int | None = None
    doc_citation: str | None = None
