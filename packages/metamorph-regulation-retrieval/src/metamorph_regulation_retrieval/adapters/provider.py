"""The regulatory provider: regulations and fatwas, clause by clause.

The provider owns the query. It embeds the question with bge-m3 in this process,
asks the index for candidates, rescoring them in full precision, and returns the
contract's evidence. There is no separate retrieval service.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any

from metamorph_regulation_retrieval.domain.citations import parse_citation
from metamorph_regulation_retrieval.domain.evidence import (
    FILTERS_EXCLUDE_ALL,
    NO_MATCH,
    document_evidence,
    evidence,
    hit,
    page,
)
from metamorph_regulation_retrieval.domain.legal import provision_label
from metamorph_regulation_retrieval.domain.refs import RefError
from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.errors import (
    CapabilityMissing,
    InvalidArgument,
    ProviderUnavailable,
    UnknownRef,
    UnknownTool,
)
from metamorph_retrieval_contract.evidence import Evidence, Hit, Page
from metamorph_retrieval_contract.links import Link
from metamorph_retrieval_contract.provider import JSON, Manifest, ToolSpec
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest, Sort

NAME = "regulation-retrieval"
VERSION = "0.1.0"
INDEX_VERSION = "METAMORPH_REGULATION_INDEX_VERSION"
DEFAULT_INDEX_VERSION = "regulation-index"
FIND = "find_provision"
KINDS = ("law", "regulation", "implementing_rule", "fatwa", "guideline", "circular", "explanatory")

FIND_TOOL = ToolSpec(
    name=FIND,
    version="0.1",
    description=(
        "Resolve a legal citation to its exact provision: 'POJK 40/2024 Pasal 137 ayat (3)', "
        "'Fatwa 117', 'UU 27/2022 Pasal 5'. Use this when the question names the regulation; it "
        "does not depend on similarity."
    ),
    input_schema={
        "type": "object",
        "properties": {"citation": {"type": "string", "minLength": 4, "maxLength": 400}},
        "required": ["citation"],
        "additionalProperties": False,
    },
    output_schema={"type": "object"},
)


class RegulationProvider:
    """Search and read over the regulation index. The store and embedder are ports."""

    def __init__(self, store, embedder, *, name: str = NAME, index_version: str | None = None) -> None:
        self.store = store
        self.embedder = embedder
        self.name = name
        self.index_version = index_version or os.environ.get(INDEX_VERSION) or DEFAULT_INDEX_VERSION

    # -- manifest ---------------------------------------------------------

    def manifest(self) -> Manifest:
        return Manifest(
            name=self.name,
            version=VERSION,
            namespaces=frozenset({"doc"}),
            kinds=frozenset(KINDS),
            links=False,
            tools=(FIND_TOOL,),
            index_version=self.index_version,
            data_as_of=self.store.published_at(),
        )

    # -- operations -------------------------------------------------------

    def search(self, request: SearchRequest) -> Page[Hit]:
        warnings = _unsupported(request)
        try:
            vector = self.embedder.encode(request.query)
            rows = self.store.search(vector, request.limit)
        except Exception as error:  # noqa: BLE001 - a failed query is ours, not the caller's
            raise ProviderUnavailable(f"{NAME} could not search: {type(error).__name__}") from error

        rows = [
            (passage, score)
            for passage, score in rows
            if (not request.kinds or passage.doc_kind in request.kinds)
            and (not request.issuers or passage.issuer in request.issuers)
        ][: request.limit]

        if not rows:
            reason = FILTERS_EXCLUDE_ALL if (request.kinds or request.issuers) else NO_MATCH
            return codec.hits_from_dict(page([], warnings=tuple(warnings), empty_reason=reason))

        items = [
            hit(passage, rank=rank, score=score, provider=self.name, index_version=self.index_version)
            for rank, (passage, score) in enumerate(rows, start=1)
        ]
        return codec.hits_from_dict(page(items, warnings=tuple(warnings)))

    def read(self, ref: Ref, *, window: int = 0) -> Evidence:
        if ref.address is None:
            document = self._document(ref)
            return codec.evidence_from_dict(
                document_evidence(document, provider=self.name, index_version=self.index_version)
            )
        try:
            passage = self.store.read(ref.id, ref.address)
        except Exception as error:  # noqa: BLE001
            raise ProviderUnavailable(f"{NAME} could not read: {type(error).__name__}") from error
        if passage is None:
            raise UnknownRef(f"{ref}: nothing is published at that address")
        return codec.evidence_from_dict(
            evidence(passage, provider=self.name, index_version=self.index_version)
        )

    def describe(self, refs: Sequence[Ref]) -> Sequence[Evidence]:
        cards: dict[Ref, Evidence] = {}
        for ref in refs:
            try:
                cards[ref] = self.read(ref).card()
            except UnknownRef:
                continue
        return [cards[ref] for ref in refs if ref in cards]

    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        raise CapabilityMissing(
            "links between regulations are not served yet; the platform publishes them and a later "
            "version of this provider will answer them"
        )

    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
        if tool != FIND:
            raise UnknownTool(f"{NAME} has no tool {tool!r}; it offers {FIND}")
        raw = str(arguments.get("citation") or "").strip()
        try:
            citation = parse_citation(raw)
        except RefError as error:
            raise InvalidArgument(str(error)) from error

        document = self._document_by_id(citation.document_id, raw)
        if citation.address is None:
            return page([document_evidence(document, provider=self.name, index_version=self.index_version)])

        try:
            passage = self.store.read(citation.document_id, citation.address)
        except Exception as error:  # noqa: BLE001
            raise ProviderUnavailable(f"{NAME} could not read: {type(error).__name__}") from error
        if passage is None:
            raise UnknownRef(
                f"{raw}: {citation.document_id} is published but {provision_label(citation.address)} is not"
            )
        return page([evidence(passage, provider=self.name, index_version=self.index_version)])

    # -- helpers ----------------------------------------------------------

    def _document(self, ref: Ref) -> dict[str, Any]:
        return self._document_by_id(ref.id, str(ref))

    def _document_by_id(self, document_id: str, shown: str) -> dict[str, Any]:
        try:
            document = self.store.document(document_id)
        except Exception as error:  # noqa: BLE001
            raise ProviderUnavailable(f"{NAME} could not read: {type(error).__name__}") from error
        if document is None:
            raise UnknownRef(f"{shown}: nothing is published under {document_id}")
        return document


def _unsupported(request: SearchRequest) -> list[str]:
    warnings: list[str] = []
    if request.documents:
        warnings.append(
            "documents: not applied; this provider searches the whole corpus, so narrow with kinds or in_force_on"
        )
    if request.published_from or request.published_to:
        warnings.append("published_from/published_to: not applied; validity is filtered with in_force_on")
    if request.legal_force:
        warnings.append("legal_force: not applied; filter on kinds instead (fatwa is sharia, regulation is binding)")
    if request.sort is not Sort.RELEVANCE:
        warnings.append("sort: newest is not offered; results are ranked by relevance")
    return warnings

