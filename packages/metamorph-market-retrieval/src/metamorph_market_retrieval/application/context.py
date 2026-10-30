"""industry_context: from a market question to the curated industry or sector, and what it links.

Each result names its register, the regulations that govern it, its reports and its datasets, all curated, never
inferred: the agent then searches within those regulations instead of hoping a search lands on them. A sector is the
curated starting point, so it comes first when it matches as well as an industry does.
"""

from __future__ import annotations

from dataclasses import dataclass

from metamorph_market_retrieval.application.paging import offset_of, paged
from metamorph_market_retrieval.application.ports import MarketReadModel, UnitFilter
from metamorph_market_retrieval.application.search import Meaning
from metamorph_market_retrieval.domain.evidence import industry_evidence, sector_evidence
from metamorph_market_retrieval.domain.fusion import reciprocal_rank_fusion
from metamorph_market_retrieval.domain.words import word_score, words
from metamorph_retrieval_contract.errors import InvalidArgument
from metamorph_retrieval_contract.evidence import EmptyReason, Evidence, Hit, MatchedBy, Page
from metamorph_retrieval_contract.requests import DEFAULT_LIMIT, check_limit

SECTOR_FIRST, INDUSTRY_NEXT = 0, 1


@dataclass(frozen=True)
class ContextQuery:
    query: str
    limit: int = DEFAULT_LIMIT
    cursor: str | None = None

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise InvalidArgument("query: say which industry, e.g. sharia fintech lending")
        check_limit(self.limit)
        offset_of(self.cursor)


class IndustryContext:
    """Sectors and industries by their names' words and, with an index, by their meaning, fused by rank: a sector
    before an industry the fusion can't tell apart, and the words' order before the key."""

    def __init__(self, read_model: MarketReadModel, *, meaning: Meaning | None = None) -> None:
        self.read_model = read_model
        self.meaning = meaning

    def run(self, query: ContextQuery) -> Page[Hit]:
        asked = words(query.query)
        cards = {str(card.evidence.ref): card for card in self._cards()}
        scored = [(word_score(asked, card.names), card.order, key) for key, card in cards.items()]
        by_words = [key for _, _, key in sorted((item for item in scored if item[0]),
                                                key=lambda item: (-item[0], item[1], item[2]))]
        by_meaning = [str(match.ref) for match in self.meaning.matches(
            query.query, UnitFilter(frozenset({"sector", "industry"})), len(cards))] if self.meaning else []
        position = {key: order for order, key in enumerate(by_words)}
        fused = sorted((item for item in reciprocal_rank_fusion([by_words, by_meaning]) if item[0] in cards),
                       key=lambda item: (-item[1], position.get(item[0], len(position)), cards[item[0]].order, item[0]))
        page = paged(fused, query.limit, query.cursor, EmptyReason.NO_MATCH)
        first_rank = offset_of(query.cursor) + 1
        return Page(tuple(
            Hit(cards[key].evidence, rank=rank, score=score,
                matched_by=frozenset({*([MatchedBy.WORDS] if key in position else []),
                                      *([MatchedBy.SEMANTIC] if key in by_meaning else [])}))
            for rank, (key, score) in enumerate(page.items, start=first_rank)
        ), page.cursor) if page.items else page

    def _cards(self) -> list[_Card]:
        return [*(_Card(SECTOR_FIRST, sector_evidence(sector), f"{sector.name} {sector.name_en or ''}")
                  for sector in self.read_model.sectors()),
                *(_Card(INDUSTRY_NEXT, industry_evidence(industry), industry.name)
                  for industry in self.read_model.industries())]


@dataclass(frozen=True)
class _Card:
    order: int  # a sector before an industry
    evidence: Evidence
    names: str  # what it is found by: its names, in each language it has one
