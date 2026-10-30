"""Searching report and release passages: full text and meaning, each over a pool of candidates, fused by rank.

Filters are applied inside both rankings, so a filter never empties a page after the fact, and are never relaxed:
an empty page says whether nothing matched or the filters excluded what did. Matches by meaning below the model's
similarity floor are dropped, so a question nothing speaks to gets no_match, not the nearest unrelated passages.
Market passages report and announce; they carry legal_force none, so a filter for binding evidence excludes them.
"""

from __future__ import annotations

from dataclasses import replace

from metamorph_market_retrieval.application.paging import offset_of
from metamorph_market_retrieval.application.ports import Embedder, MarketReadModel, Match, SearchIndex, UnitFilter
from metamorph_market_retrieval.domain.evidence import passage_evidence
from metamorph_market_retrieval.domain.fusion import reciprocal_rank_fusion
from metamorph_retrieval_contract.evidence import EmptyReason, Evidence, Hit, LegalForce, MatchedBy, Page
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import SearchRequest, Sort

PASSAGE_KINDS = frozenset({"report", "release"})
CANDIDATES = 50  # from each ranking, before fusion
NOT_BINDING = "legal_force: report and release passages are none; search the regulations for binding evidence"
NOT_IN_FORCE = "in_force_on: applies to regulations; report and release passages were kept as published"


class Meaning:
    """Matches by meaning from one index version: the question embedded by the version's model, and matches below
    the model's similarity floor dropped."""

    def __init__(self, index: SearchIndex, embedder: Embedder, *, min_similarity: float) -> None:
        if embedder.model != index.model:
            raise ValueError(f"{index.version} holds {index.model} vectors; {embedder.model} can't search them")
        self.index = index
        self.embedder = embedder
        self.min_similarity = min_similarity

    def matches(self, query: str, where: UnitFilter, limit: int) -> list[Match]:
        (vector,) = self.embedder.embed_queries([query])
        return [match for match in self.index.by_meaning(vector, where, limit) if match.score >= self.min_similarity]


class SearchPassages:
    def __init__(self, read_model: MarketReadModel, index: SearchIndex, meaning: Meaning | None = None) -> None:
        self.read_model = read_model
        self.index = index
        self.meaning = meaning

    def run(self, request: SearchRequest) -> Page[Hit]:
        warnings = [NOT_IN_FORCE] if request.in_force_on else []
        if request.legal_force and LegalForce.NONE not in request.legal_force:
            return Page.empty(EmptyReason.FILTERS_EXCLUDE_ALL, (NOT_BINDING,))
        where = _filter(request)
        if where is None:
            return Page.empty(EmptyReason.FILTERS_EXCLUDE_ALL, tuple(warnings))
        words, meaning = self._matches(request.query, where)
        fused = reciprocal_rank_fusion([[str(match.ref) for match in words], [str(match.ref) for match in meaning]])
        if not fused:
            return Page.empty(self._why_empty(request.query, where), tuple(warnings))
        if request.sort is Sort.NEWEST:
            dates = {str(match.ref): match.published_on for match in (*words, *meaning)}
            fused.sort(key=lambda item: -(dates[item[0]].toordinal() if dates[item[0]] else 0))  # stable: ties by rank
        start = offset_of(request.cursor)
        by_words, by_meaning = {str(match.ref) for match in words}, {str(match.ref) for match in meaning}
        hits, gone = [], 0
        for rank, (key, score) in enumerate(fused[start: start + request.limit], start=start + 1):
            evidence = self._evidence(Ref.parse(key))
            if evidence is None:
                gone += 1
                continue
            matched = {MatchedBy.WORDS} if key in by_words else set()
            hits.append(Hit(evidence, rank=rank - gone, score=score,
                            matched_by=frozenset(matched | ({MatchedBy.SEMANTIC} if key in by_meaning else set()))))
        if gone:
            warnings.append(f"{gone} found in the index is no longer published; the index is older than the data")
        if not hits:
            return Page.empty(EmptyReason.NO_MATCH, tuple(warnings))
        following = start + request.limit
        return Page(tuple(hits), cursor=str(following) if following < len(fused) else None, warnings=tuple(warnings))

    def _matches(self, query: str, where: UnitFilter) -> tuple[list[Match], list[Match]]:
        words = self.index.by_words(query, where, CANDIDATES)
        return words, self.meaning.matches(query, where, CANDIDATES) if self.meaning else []

    def _why_empty(self, query: str, where: UnitFilter) -> EmptyReason:
        unfiltered = UnitFilter(PASSAGE_KINDS)
        if where != unfiltered and any(self._matches(query, unfiltered)):
            return EmptyReason.FILTERS_EXCLUDE_ALL
        return EmptyReason.NO_MATCH

    def _evidence(self, ref: Ref) -> Evidence | None:
        assert ref.address is not None
        found = self.read_model.passages(ref.namespace, ref.id, ref.address, 0)
        if not found:
            return None
        evidence = passage_evidence(found[0])
        return replace(evidence, provenance=replace(evidence.provenance, index_version=self.index.version))


def _filter(request: SearchRequest) -> UnitFilter | None:
    """The request's filters, as the index applies them; None when they leave no market passage to search."""
    kinds = (request.kinds or PASSAGE_KINDS) & PASSAGE_KINDS
    documents = frozenset(ref for ref in request.documents if ref.namespace in PASSAGE_KINDS)
    if not kinds or (request.documents and not documents):
        return None
    return UnitFilter(kinds=kinds, issuers=frozenset(issuer.casefold() for issuer in request.issuers),
                      documents=documents, published_from=request.published_from, published_to=request.published_to)

