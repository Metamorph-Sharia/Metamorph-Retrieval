"""Providers for the gateway's tests: the contract's memory provider, and two more that own what it doesn't.

`Regulations` owns `doc:` and holds one regulation, as the stand-in will. `Industries` owns `industry:` and has one
tool whose records name regulations by `{"ref": …}` stubs, as the market's do.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from retrieval_samples import PUBLISHED_AT, provenance, regulation

from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.errors import CapabilityMissing, UnknownRef, UnknownTool
from metamorph_retrieval_contract.evidence import Evidence, Hit, LegalForce, Page, Qualifiers, Record
from metamorph_retrieval_contract.links import Link
from metamorph_retrieval_contract.provider import JSON, Manifest, ToolSpec
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest
from metamorph_retrieval_contract.schema import shape_schema
from metamorph_retrieval_gateway.application.calls import Call

POJK_40 = Ref.parse("doc:ojk:pojk:2024:40")
UNPUBLISHED = Ref.parse("doc:ojk:pojk:2099:1")  # named by a report, not published yet
SHARIA_LENDING = Ref.parse("industry:ojk:portal:lpbbti-syariah")


class Regulations:
    def __init__(self, evidence: Sequence[Evidence] = (regulation(),), *, delay: float = 0.0) -> None:
        self.evidence = {item.ref: item for item in evidence}
        self.delay = delay
        self.described: list[list[Ref]] = []

    def manifest(self) -> Manifest:
        return Manifest(name="regulation", version="0.1.0", namespaces=frozenset({"doc"}), kinds=frozenset(),
                        links=False, tools=(), index_version="published-sql", data_as_of=PUBLISHED_AT)

    def search(self, request: SearchRequest) -> Page[Hit]:
        raise CapabilityMissing("regulation has no search")

    def read(self, ref: Ref, *, window: int = 0) -> Evidence:
        if ref not in self.evidence:
            raise UnknownRef(f"regulation holds nothing under {ref}")
        return self.evidence[ref]

    def describe(self, refs: Sequence[Ref]) -> Sequence[Evidence]:
        time.sleep(self.delay)
        self.described.append(list(refs))
        return [self.evidence[ref].card() for ref in refs if ref in self.evidence]

    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        raise CapabilityMissing("regulation has no links")

    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
        raise UnknownTool(f"regulation has no tool {tool}")


def industry(named: Sequence[Ref] = (POJK_40, UNPUBLISHED)) -> Evidence:
    return Evidence(
        ref=SHARIA_LENDING,
        kind="industry",
        citation="OJK, Statistik LPBBTI Syariah",
        title="LPBBTI Syariah",
        legal_force=LegalForce.NONE,
        qualifiers=Qualifiers(),
        published_on=None,
        url=None,
        body=Record({"register": "ojk:lpbbti", "governed_by": [{"ref": str(ref)} for ref in named]}),
        provenance=provenance(),
    )


CONTEXT = ToolSpec(
    name="industry_context",
    version="0.1",
    description="An industry's regulations.",
    input_schema={"type": "object", "additionalProperties": False, "properties": {"query": {"type": "string"}}},
    output_schema=shape_schema("evidence_page"),
)


class Industries:
    """Raises, sleeps or answers, as a test needs."""

    def __init__(self, evidence: Evidence | None = None, *, delay: float = 0.0, fails: Exception | None = None) -> None:
        self.evidence = evidence or industry()
        self.delay = delay
        self.fails = fails

    def manifest(self) -> Manifest:
        return Manifest(name="industries", version="0.1.0", namespaces=frozenset({"industry"}), kinds=frozenset(),
                        links=False, tools=(CONTEXT,), index_version="industries-1", data_as_of=PUBLISHED_AT)

    def search(self, request: SearchRequest) -> Page[Hit]:
        raise CapabilityMissing("industries has no search")

    def read(self, ref: Ref, *, window: int = 0) -> Evidence:
        self._misbehave()
        if ref != self.evidence.ref:
            raise UnknownRef(f"industries holds nothing under {ref}")
        return self.evidence

    def describe(self, refs: Sequence[Ref]) -> Sequence[Evidence]:
        return [self.evidence.card() for ref in refs if ref == self.evidence.ref]

    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        raise CapabilityMissing("industries has no links")

    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
        self._misbehave()
        if tool != CONTEXT.name:
            raise UnknownTool(f"industries has no tool {tool}")
        return codec.to_dict(Page((self.evidence,)))

    def _misbehave(self) -> None:
        time.sleep(self.delay)
        if self.fails:
            raise self.fails


def renamed(provider: Any, name: str, **changes: Any) -> Any:
    """The provider, with its manifest renamed and changed: two providers claiming one namespace or one tool."""

    class Renamed:
        def __getattr__(self, attribute: str) -> Any:
            return getattr(provider, attribute)

        def manifest(self) -> Manifest:
            return replace(provider.manifest(), name=name, **changes)

    return Renamed()


class Recorded:
    """A call log that keeps the calls, to look at."""

    def __init__(self) -> None:
        self.calls: list[Call] = []

    def record(self, call: Call) -> None:
        self.calls.append(call)


def regulations() -> Regulations:
    """A factory, as the wiring names one: module:function."""
    return Regulations()


def industries() -> Industries:
    return Industries()


NOT_A_FACTORY = "a string"
