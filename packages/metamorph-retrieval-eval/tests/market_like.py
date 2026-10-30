"""A provider shaped like the market provider will be: memory's evidence and links, and two tools that return pages
of evidence, one with figures and one naming regulations in its fields."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from memory_provider import MANIFEST, MemoryProvider
from retrieval_samples import m2_series, provenance

from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.errors import UnknownTool
from metamorph_retrieval_contract.evidence import Evidence, Hit, LegalForce, MatchedBy, Page, Qualifiers, Record
from metamorph_retrieval_contract.provider import JSON
from metamorph_retrieval_contract.refs import Ref

LPBBTI_SYARIAH = Ref.parse("industry:ojk:portal:lpbbti-syariah")


def industry() -> Evidence:
    return Evidence(
        ref=LPBBTI_SYARIAH,
        kind="industry",
        citation="OJK, Statistik LPBBTI Syariah",
        title="Layanan Pendanaan Bersama Berbasis Teknologi Informasi (LPBBTI) Syariah",
        legal_force=LegalForce.NONE,
        qualifiers=Qualifiers(),
        published_on=None,
        url=None,
        body=Record({
            "register": {"ref": "register:ojk:lpbbti"},
            "governed_by": [{"ref": "doc:ojk:pojk:2024:40"}, {"ref": "doc:ojk:seojk:2025:19"}],
        }),
        provenance=provenance(),
    )


class MarketLike(MemoryProvider):
    def __init__(self) -> None:
        super().__init__(manifest=replace(MANIFEST, namespaces=MANIFEST.namespaces | {"series", "industry"}))

    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
        if tool == "find_series":
            hit = Hit(m2_series(), rank=1, score=0.9, matched_by=frozenset({MatchedBy.WORDS}))
            return codec.to_dict(Page((hit,)))
        if tool == "industry_context":
            return codec.to_dict(Page((industry(),)))
        if tool == "broken":
            return {"items": [{"ref": "series:x:y"}]}
        raise UnknownTool(f"no tool {tool}")
