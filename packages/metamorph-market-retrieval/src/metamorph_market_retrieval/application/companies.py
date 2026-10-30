"""find_companies: who is licensed, registered or gone, by name or by filter, today or on a past date.

Without a name, the companies filtered come by legal name, as evidence. With one, they come ranked by how well a name
of theirs matches it, as hits. On a past date (`as_of`), the register's edition current that day decides who was
listed and their standing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from metamorph_market_retrieval.application.paging import offset_of, paged
from metamorph_market_retrieval.application.ports import MarketReadModel
from metamorph_market_retrieval.domain.evidence import company_evidence
from metamorph_market_retrieval.domain.names import rank_by_name
from metamorph_market_retrieval.domain.records import Company
from metamorph_market_retrieval.domain.standing import standing_on
from metamorph_retrieval_contract.errors import InvalidArgument
from metamorph_retrieval_contract.evidence import EmptyReason, Evidence, Hit, MatchedBy, Page
from metamorph_retrieval_contract.requests import DEFAULT_LIMIT, check_limit

STATUSES = ("licensed", "registered", "left")
BUSINESS_TYPES = ("sharia", "conventional", "unknown")


@dataclass(frozen=True)
class CompanyQuery:
    register: str | None = None
    query: str | None = None  # a legal or platform name, or part of one
    status: str | None = None
    business_type: str | None = None
    as_of: date | None = None
    announcements: bool = False  # also the release passages naming each company
    limit: int = DEFAULT_LIMIT
    cursor: str | None = None

    def __post_init__(self) -> None:
        if self.status is not None and self.status not in STATUSES:
            raise InvalidArgument(f"status {self.status!r}: licensed, registered or left")
        if self.business_type is not None and self.business_type not in BUSINESS_TYPES:
            raise InvalidArgument(f"business_type {self.business_type!r}: sharia, conventional or unknown")
        if self.status == "left" and self.as_of is not None:
            raise InvalidArgument("status left: a company that left isn't on that day's edition; ask without as_of")
        if self.query is not None and not self.query.strip():
            raise InvalidArgument("query: say which name, or leave it out")
        check_limit(self.limit)
        offset_of(self.cursor)


@dataclass(frozen=True)
class _Candidate:
    company: Company
    standing: str | None = None  # on a past edition; None: today's
    edition: date | None = None


class FindCompanies:
    def __init__(self, read_model: MarketReadModel) -> None:
        self.read_model = read_model

    def run(self, query: CompanyQuery) -> Page[Hit] | Page[Evidence]:
        candidates = self._candidates(query)
        if not candidates:
            return Page.empty(EmptyReason.FILTERS_EXCLUDE_ALL)
        if query.query is None:
            return self._by_legal_name(candidates, query)
        return self._by_name(query.query, candidates, query)

    def _by_legal_name(self, candidates: Sequence[_Candidate], query: CompanyQuery) -> Page[Evidence]:
        ordered = sorted(candidates, key=lambda candidate: (candidate.company.legal_name.casefold(),
                                                            candidate.company.id))
        page = paged(ordered, query.limit, query.cursor, EmptyReason.NO_MATCH)
        return Page(self._evidence(page.items, query), page.cursor)

    def _by_name(self, name: str, candidates: Sequence[_Candidate], query: CompanyQuery) -> Page[Hit]:
        by_id = {candidate.company.id: candidate for candidate in candidates}
        ranked = rank_by_name(name, {key: (c.company.legal_name, *c.company.names) for key, c in by_id.items()})
        page = paged(ranked, query.limit, query.cursor, EmptyReason.NO_MATCH)
        if not page.items:
            return Page.empty(EmptyReason.NO_MATCH)
        evidence = self._evidence([by_id[key] for key, _ in page.items], query)
        first_rank = offset_of(query.cursor) + 1
        return Page(tuple(
            Hit(item, rank=rank, score=match.score, matched_by=frozenset({MatchedBy.WORDS}))
            for rank, (item, (_, match)) in enumerate(zip(evidence, page.items, strict=True), start=first_rank)
        ), page.cursor)

    def _candidates(self, query: CompanyQuery) -> list[_Candidate]:
        if query.as_of is None:
            return [_Candidate(company) for company in
                    self.read_model.companies(query.register, query.status, query.business_type)]
        listed = [_Candidate(item.company, standing_on(item.kinds), item.edition)
                  for item in self.read_model.listed_on(query.register, query.as_of)]
        return [candidate for candidate in listed
                if (query.status is None or candidate.standing == query.status)
                and (query.business_type is None or candidate.company.business_type == query.business_type)]

    def _evidence(self, candidates: Sequence[_Candidate], query: CompanyQuery) -> tuple[Evidence, ...]:
        announced = (self.read_model.announcements([candidate.company.id for candidate in candidates])
                     if query.announcements else {})
        return tuple(
            company_evidence(candidate.company, standing=candidate.standing, edition=candidate.edition,
                             announcements=announced.get(candidate.company.id, ()))
            for candidate in candidates
        )
