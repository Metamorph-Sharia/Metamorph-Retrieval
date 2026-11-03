"""The evidence envelope the contract asks for: what a passage says, how to cite
it, and how much it counts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from metamorph_regulation_retrieval.domain.legal import document_citation, legal_force_of, provision_label
from metamorph_regulation_retrieval.domain.passage import Passage
from metamorph_regulation_retrieval.domain.refs import make_ref

NO_MATCH = "no_match"
FILTERS_EXCLUDE_ALL = "filters_exclude_all"


def page(items: list[dict[str, Any]], *, warnings: tuple[str, ...] = (), empty_reason: str | None = None):
    if not items and empty_reason is None:
        empty_reason = NO_MATCH
    return {
        "items": items,
        "cursor": None,
        "empty_reason": empty_reason if not items else None,
        "warnings": list(warnings),
    }


def hit(passage: Passage, *, rank: int, score: float, provider: str, index_version: str):
    return {
        "rank": rank,
        "score": float(score),
        "matched_by": ["semantic"],
        "evidence": evidence(passage, provider=provider, index_version=index_version),
    }


def evidence(passage: Passage, *, provider: str, index_version: str):
    return {
        "ref": make_ref(passage.document_id, passage.address),
        "kind": passage.doc_kind or "regulation",
        "citation": _citation(passage),
        "title": passage.title,
        "legal_force": legal_force_of(passage.doc_kind),
        "qualifiers": {
            "status": passage.doc_status,
            "valid_from": _date(passage.valid_from or passage.effective_on),
            "valid_to": _date(passage.valid_to),
            "under_review": False,
            "provisional": False,
            "as_of": None,
        },
        "published_on": _date(passage.promulgated_on),
        "url": None,
        "body": {"type": "text", "wording": passage.text, "pages": None},
        "provenance": {
            "provider": provider,
            "index_version": index_version,
            "source_published_at": _datetime(passage.published_at),
        },
    }


def document_evidence(document: dict[str, Any], *, provider: str, index_version: str):
    return {
        "ref": make_ref(document["document_id"]),
        "kind": document.get("kind") or "regulation",
        "citation": document_citation(
            document.get("citation"), document.get("family"), document.get("number"), document.get("year")
        ) or document["document_id"],
        "title": document.get("title") or "",
        "legal_force": legal_force_of(document.get("kind")),
        "qualifiers": {
            "status": document.get("status"),
            "valid_from": _date(document.get("effective_on")),
            "valid_to": None,
            "under_review": False,
            "provisional": False,
            "as_of": None,
        },
        "published_on": _date(document.get("promulgated_on")),
        "url": None,
        "body": {
            "type": "record",
            "fields": {
                "issuer": document.get("issuer"),
                "family": document.get("family"),
                "number": document.get("number"),
                "year": document.get("year"),
                "effective_on": _date(document.get("effective_on")),
                "aliases": list(document.get("aliases") or ()),
            },
        },
        "provenance": {
            "provider": provider,
            "index_version": index_version,
            "source_published_at": _datetime(document.get("published_at")),
        },
    }


def _citation(passage: Passage) -> str:
    label = provision_label(passage.address)
    base = document_citation(
        passage.doc_citation, passage.family, passage.number, passage.year
    ) or passage.title or passage.document_id
    return f"{base}, {label}" if label else base


def _date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).isoformat()
    return str(value or "1970-01-01T00:00:00+00:00")
