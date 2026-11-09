"""The regulatory provider: regulations and fatwas, clause by clause.

The provider owns the query. It embeds the question with bge-m3 in this process,
asks the index for candidates, rescoring them in full precision, and returns the
contract's evidence. There is no separate retrieval service.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import replace
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
from metamorph_regulation_retrieval.domain.filters import Filters
from metamorph_regulation_retrieval.domain.fusion import reciprocal_rank_fusion
from metamorph_regulation_retrieval.domain.legal import legal_force_of, provision_label
from metamorph_regulation_retrieval.domain.links import CONFIDENCE, LinkRow
from metamorph_regulation_retrieval.domain.passage import Passage
from metamorph_regulation_retrieval.domain.refs import NAMESPACE, RefError
from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.errors import (
    InvalidArgument,
    ProviderUnavailable,
    UnknownRef,
    UnknownTool,
)
from metamorph_retrieval_contract.evidence import EmptyReason, Evidence, Hit, Page
from metamorph_retrieval_contract.links import Direction, Link, LinkType
from metamorph_retrieval_contract.provider import JSON, Manifest, ToolSpec
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest, Sort

NAME = "regulation-retrieval"
VERSION = "0.1.0"
INDEX_VERSION = "METAMORPH_REGULATION_INDEX_VERSION"
DEFAULT_INDEX_VERSION = "regulation-index"
FIND = "find_provision"
KINDS = ("law", "regulation", "implementing_rule", "fatwa", "guideline", "circular", "explanatory")
MAX_DEPTH = 50  # how far down the fused ranking a cursor can page
# A hit shows at most this much of its unit, about a market passage's length, so a page of long units (an SEOJK part,
# a fatwa's decision) stays within what one call may return; `read` gives the whole.
HIT_CHARS = 3_000
SHORTENED = f"a hit ending in … shows the first {HIT_CHARS:,} characters of a long unit; read its ref for the whole"
CANDIDATES = MAX_DEPTH  # each ranking's candidates for fusion
WORDS, SEMANTIC = "words", "semantic"
NO_WORDS = "matched by meaning only: this index predates word search; rebuild it to match words too"
NOT_DATED = ("in_force_on: revocations are not dated in this index, so documents revoked today were left out on "
             "every day; rebuild the index to date them")

NO_LINKS = "links are not served: this index predates them; rebuild it to follow what amends or revokes a regulation"

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
            kinds=self.store.kinds(),  # those held: narrowing to another would only empty the page
            links=True,
            tools=(FIND_TOOL,),
            index_version=self.index_version,
            data_as_of=self.store.published_at(),
        )

    # -- operations -------------------------------------------------------

    def search(self, request: SearchRequest) -> Page[Hit]:
        filters, warnings = _filters(request)
        if filters is None:
            return codec.hits_from_dict(page([], warnings=tuple(warnings), empty_reason=FILTERS_EXCLUDE_ALL))
        start = _offset(request.cursor)
        depth = min(start + request.limit, MAX_DEPTH)
        try:
            vector = self.embedder.encode(request.query)
            by_meaning = self.store.by_meaning(vector, CANDIDATES, filters)
            by_words = self.store.by_words(request.query, CANDIDATES, filters) if self.store.matches_words() else []
            if not self.store.matches_words():
                warnings.append(NO_WORDS)
            if filters.in_force_on and not self.store.dates_revocations():
                warnings.append(NOT_DATED)
        except Exception as error:  # noqa: BLE001 - a failed query is ours, not the caller's
            raise ProviderUnavailable(f"{NAME} could not search: {type(error).__name__}") from error

        passages = {passage.chunk_id: passage for passage, _ in (*by_meaning, *by_words)}
        meaning_keys = [passage.chunk_id for passage, _ in by_meaning]
        words_keys = [passage.chunk_id for passage, _ in by_words]
        fused = reciprocal_rank_fusion([meaning_keys, words_keys])
        chosen = fused[start:depth]
        if not chosen:
            reason = FILTERS_EXCLUDE_ALL if filters and not fused else NO_MATCH  # past the last page: no match
            return codec.hits_from_dict(page([], warnings=tuple(warnings), empty_reason=reason))

        found_by = {key: [name for name, keys in ((WORDS, words_keys), (SEMANTIC, meaning_keys)) if key in keys]
                    for key, _ in chosen}
        shown = {key: _shortened(passages[key]) for key, _ in chosen}
        items = [
            hit(shown[key], rank=rank, score=score, provider=self.name, index_version=self.index_version,
                matched_by=found_by[key])
            for rank, (key, score) in enumerate(chosen, start=start + 1)
        ]
        if any(shown[key] is not passages[key] for key, _ in chosen):
            warnings.append(SHORTENED)
        following = depth if depth < min(len(fused), MAX_DEPTH) else None
        return codec.hits_from_dict(page(items, warnings=tuple(warnings), cursor=following))

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
        if ref.namespace != NAMESPACE:
            return Page.empty(EmptyReason.NO_MATCH)
        if not self.store.holds_links():
            return Page.empty(EmptyReason.NO_MATCH, (NO_LINKS,))
        offset = _offset(request.cursor)
        try:
            rows = self.store.links(
                ref.id, ref.address,
                incoming=request.direction is not Direction.OUTGOING,
                outgoing=request.direction is not Direction.INCOMING,
                types=sorted(request.types),
                limit=request.limit + 1,
                offset=offset,
            )
        except Exception as error:  # noqa: BLE001
            raise ProviderUnavailable(f"{NAME} could not read links: {type(error).__name__}") from error
        links = tuple(_link(row) for row in rows[: request.limit])
        if not links:
            return Page.empty(EmptyReason.NO_MATCH)
        return Page(links, cursor=str(offset + request.limit) if len(rows) > request.limit else None)

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


def _filters(request: SearchRequest) -> tuple[Filters | None, list[str]]:
    """The request in the index's terms, and what it asked that the index can't apply. None: nothing can match."""
    kinds = frozenset(request.kinds)  # empty: not narrowed
    if request.legal_force:
        kinds = frozenset(kind for kind in kinds or KINDS if legal_force_of(kind) in request.legal_force)
    warnings: list[str] = []
    if request.published_from or request.published_to:
        warnings.append("published_from/published_to: not applied; they date reports and releases, and a "
                        "regulation's validity is filtered with in_force_on")
    if request.sort is not Sort.RELEVANCE:
        warnings.append("sort: newest is not offered; results are ranked by relevance")
    if (request.kinds or request.legal_force) and not kinds & frozenset(KINDS):
        return None, warnings
    documents = tuple(ref.id for ref in request.documents)
    return Filters(kinds, frozenset(request.issuers), documents, request.in_force_on), warnings


def _shortened(passage: Passage) -> Passage:
    """The passage, its wording cut at a word to HIT_CHARS when it is longer."""
    if len(passage.text) <= HIT_CHARS:
        return passage
    return replace(passage, text=passage.text[:HIT_CHARS].rsplit(" ", 1)[0] + "…")


def _link(row: LinkRow) -> Link:
    return Link(LinkType(row.type), Ref(NAMESPACE, row.from_document, row.from_address),
                Ref(NAMESPACE, row.to_document, row.to_address), effective_on=row.effective_on,
                confidence=CONFIDENCE.get(row.confidence or ""))


def _offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isdigit():
        raise InvalidArgument(f"cursor {cursor!r} is not one this provider gave; leave it out for the first page")
    return int(cursor)
