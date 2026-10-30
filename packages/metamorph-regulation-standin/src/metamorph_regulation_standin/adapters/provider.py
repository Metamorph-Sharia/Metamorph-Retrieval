"""The stand-in, as the retrieval contract has it: it owns `doc:` refs and reads them; nothing else.

It keeps market answers' regulation citations working end to end, and the contract honest about a second
provider, until the regulatory provider replaces it (retrieval-architecture.md §10).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from metamorph_regulation_standin.application.ports import RegulationReadModel
from metamorph_regulation_standin.application.reading import Reading
from metamorph_regulation_standin.domain.evidence import INDEX_VERSION, NAMESPACE, PROVIDER
from metamorph_retrieval_contract.errors import CapabilityMissing, UnknownTool
from metamorph_retrieval_contract.evidence import Evidence, Hit, Page
from metamorph_retrieval_contract.links import Link
from metamorph_retrieval_contract.provider import JSON, Manifest
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest

VERSION = "0.1.0"


class StandinProvider:
    def __init__(self, read_model: RegulationReadModel) -> None:
        self.read_model = read_model
        self.reading = Reading(read_model)

    def manifest(self) -> Manifest:
        return Manifest(name=PROVIDER, version=VERSION, namespaces=frozenset({NAMESPACE}), kinds=frozenset(),
                        links=False, tools=(), index_version=INDEX_VERSION, data_as_of=self.read_model.published_at())

    def search(self, request: SearchRequest) -> Page[Hit]:
        raise CapabilityMissing("regulations can be read and described by ref, not searched, until the regulatory "
                                "provider joins; industry_context names an industry's regulations")

    def read(self, ref: Ref, *, window: int = 0) -> Evidence:
        return self.reading.read(ref)

    def describe(self, refs: Sequence[Ref]) -> Sequence[Evidence]:
        return self.reading.describe(refs)

    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        raise CapabilityMissing("links between regulations arrive with the regulatory provider")

    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
        raise UnknownTool(f"{PROVIDER} has no tools")
