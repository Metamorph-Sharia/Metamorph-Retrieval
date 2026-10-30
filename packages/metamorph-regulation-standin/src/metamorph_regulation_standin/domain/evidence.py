"""Documents and provisions as evidence, with the legal force their kind gives them.

A provision is cited by its document's citation and its address, printed as lawyers write it: the address grammar
is the read contract's (published-schema.md), so the label is read from it, never from one document's layout.
"""

from __future__ import annotations

from datetime import date

from metamorph_regulation_standin.domain.records import Document, Unit
from metamorph_retrieval_contract.evidence import (
    Evidence,
    LegalForce,
    PageSpan,
    Provenance,
    Qualifiers,
    Record,
    Text,
)
from metamorph_retrieval_contract.refs import Ref

PROVIDER = "regulation-standin"
INDEX_VERSION = "published-sql"
NAMESPACE = "doc"

LEGAL_FORCE = {  # retrieval-tools-design.md, "Legal force"
    "law": LegalForce.BINDING,
    "regulation": LegalForce.BINDING,
    "implementing_rule": LegalForce.BINDING,
    "fatwa": LegalForce.SHARIA,
    "guideline": LegalForce.SHARIA,
    "circular": LegalForce.SHARIA,  # DSN-MUI's; the issuers' circulars are published as implementing rules
    "explanatory": LegalForce.EXPLANATORY,
}
NUMBERED = {"pasal": "Pasal {}", "ayat": "ayat ({})", "huruf": "huruf {}", "angka": "angka {}", "bab": "BAB {}",
            "lampiran": "Lampiran {}", "romawi": "{}"}
ROMAN_NUMBERED = {"bab", "lampiran", "romawi"}
ROMAN = set("ivxlcdm")


def legal_force_of(kind: str) -> LegalForce:
    if kind not in LEGAL_FORCE:
        raise ValueError(f"kind {kind!r} has no legal force yet; add it to LEGAL_FORCE from the tools design")
    return LEGAL_FORCE[kind]


def provision_label(address: str) -> str:
    """`pasal-5/ayat-1/huruf-a` → `Pasal 5 ayat (1) huruf a`."""
    return " ".join(_segment(segment) for segment in address.split("/"))


def _segment(segment: str) -> str:
    word, _, number = segment.partition("-")
    if word in NUMBERED and number:
        roman = word in ROMAN_NUMBERED or (word == "pasal" and set(number) <= ROMAN)
        return NUMBERED[word].format(number.upper() if roman else number)
    return " ".join(part.capitalize() for part in segment.split("-"))


def document_evidence(document: Document) -> Evidence:
    return Evidence(
        ref=Ref(NAMESPACE, document.id),
        kind=document.kind,
        citation=document.citation,
        title=document.title,
        legal_force=legal_force_of(document.kind),
        qualifiers=Qualifiers(status=document.status, valid_from=document.effective_on, as_of=document.status_as_of),
        published_on=document.promulgated_on,
        url=None,
        body=Record({
            "issuer": document.issuer, "family": document.family, "number": document.number, "year": document.year,
            "enacted_on": _day(document.enacted_on), "promulgated_on": _day(document.promulgated_on),
            "effective_on": _day(document.effective_on), "aliases": list(document.aliases),
        }),
        provenance=_provenance(document),
    )


def unit_evidence(unit: Unit) -> Evidence:
    document = unit.document
    pages = PageSpan(unit.page_start, unit.page_end) if unit.page_start and unit.page_end else None
    return Evidence(
        ref=Ref(NAMESPACE, document.id, unit.address),
        kind=document.kind,
        citation=f"{document.citation}, {provision_label(unit.address)}",
        title=document.title,
        legal_force=legal_force_of(document.kind),
        qualifiers=Qualifiers(status=document.status, valid_from=unit.valid_from or document.effective_on,
                              valid_to=unit.valid_to, under_review=unit.under_review, as_of=document.status_as_of),
        published_on=document.promulgated_on,
        url=None,
        body=Text(unit.wording, pages),
        provenance=_provenance(document),
    )


def _provenance(document: Document) -> Provenance:
    return Provenance(provider=PROVIDER, index_version=INDEX_VERSION, source_published_at=document.published_at)


def _day(value: date | None) -> str | None:
    return value.isoformat() if value else None
