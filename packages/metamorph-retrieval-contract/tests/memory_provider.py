"""A provider over a few pieces of evidence held in memory: the smallest thing that keeps the contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from retrieval_samples import PUBLISHED_AT, release_passage, report_passage

from metamorph_retrieval_contract.errors import CapabilityMissing, UnknownRef, UnknownTool
from metamorph_retrieval_contract.evidence import EmptyReason, Evidence, Hit, MatchedBy, Page, Text
from metamorph_retrieval_contract.links import Link, LinkType
from metamorph_retrieval_contract.provider import JSON, Manifest, ToolSpec
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest

COUNT = ToolSpec(
    name="count",
    version="0.1",
    description="How many pieces of evidence of a kind it holds.",
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["kind"],
        "properties": {"kind": {"type": "string"}},
    },
    output_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["count"],
        "properties": {"count": {"type": "integer", "minimum": 0}},
    },
)

MANIFEST = Manifest(
    name="memory",
    version="0.1.0",
    namespaces=frozenset({"report", "release"}),
    kinds=frozenset({"report", "release"}),
    links=True,
    tools=(COUNT,),
    index_version="memory-1",
    data_as_of=PUBLISHED_AT,
)

POJK_40 = Ref.parse("doc:ojk:pojk:2024:40")
NAMES_POJK_40 = Link(LinkType.NAMES, source=release_passage().ref, target=POJK_40)  # a regulation memory doesn't own


class MemoryProvider:
    def __init__(
        self,
        evidence: Sequence[Evidence] = (report_passage(), release_passage()),
        links: Sequence[Link] = (NAMES_POJK_40,),
        manifest: Manifest = MANIFEST,
    ) -> None:
        self.evidence = {item.ref: item for item in evidence}
        self.all_links = tuple(links)
        self.declared = manifest

    def manifest(self) -> Manifest:
        return self.declared

    def search(self, request: SearchRequest) -> Page[Hit]:
        if not self.declared.kinds:
            raise CapabilityMissing("memory has no search")
        words = set(request.query.lower().split())
        scored = sorted(
            ((len(words & _words(item)), item) for item in self.evidence.values() if _searchable(item, request)),
            key=lambda pair: (-pair[0], str(pair[1].ref)),
        )
        matches = [(score, item) for score, item in scored if score]
        if not matches:
            return Page.empty(EmptyReason.NO_MATCH)
        return Page(
            tuple(
                Hit(item, rank=rank, score=float(score), matched_by=frozenset({MatchedBy.WORDS}))
                for rank, (score, item) in enumerate(matches[: request.limit], start=1)
            )
        )

    def read(self, ref: Ref, *, window: int = 0) -> Evidence:
        if ref not in self.evidence:
            raise UnknownRef(f"memory holds nothing under {ref}")
        return self.evidence[ref]

    def describe(self, refs: Sequence[Ref]) -> Sequence[Evidence]:
        return [self.evidence[ref].card() for ref in refs if ref in self.evidence]

    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        if not self.declared.links:
            raise CapabilityMissing("memory has no links")
        found = tuple(link for link in self.all_links if ref in (link.source, link.target))
        return Page(found[: request.limit]) if found else Page.empty(EmptyReason.NO_MATCH)

    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
        if tool != COUNT.name:
            raise UnknownTool(f"memory has no tool {tool}")
        return {"count": sum(1 for item in self.evidence.values() if item.kind == arguments["kind"])}


def _searchable(item: Evidence, request: SearchRequest) -> bool:
    return isinstance(item.body, Text) and (not request.kinds or item.kind in request.kinds)


def _words(item: Evidence) -> set[str]:
    assert isinstance(item.body, Text)
    return set(f"{item.title} {item.body.wording}".lower().split())
