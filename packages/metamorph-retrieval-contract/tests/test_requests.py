from datetime import date

import pytest

from metamorph_retrieval_contract.errors import InvalidArgument
from metamorph_retrieval_contract.links import Direction, Link, LinkType
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import MAX_LIMIT, LinksRequest, SearchRequest, Sort


def test_a_search_asks_for_eight_results_by_relevance_with_no_filters() -> None:
    request = SearchRequest("persyaratan perizinan penyelenggara")

    assert (request.limit, request.sort, request.kinds, request.documents) == (8, Sort.RELEVANCE, frozenset(), ())


def test_a_blank_query_is_refused() -> None:
    with pytest.raises(InvalidArgument, match="query: say what to search for"):
        SearchRequest("  ")


def test_more_than_the_maximum_is_refused_and_says_the_maximum() -> None:
    with pytest.raises(InvalidArgument, match=f"limit 26: at most {MAX_LIMIT}"):
        SearchRequest("pembiayaan", limit=26)
    with pytest.raises(InvalidArgument, match="limit 0"):
        SearchRequest("pembiayaan", limit=0)


def test_dates_in_the_wrong_order_are_refused() -> None:
    with pytest.raises(InvalidArgument, match="published_from 2026-10-01 is after published_to 2026-01-01"):
        SearchRequest("cabut izin", published_from=date(2026, 10, 1), published_to=date(2026, 1, 1))


def test_documents_to_search_within_are_whole_documents() -> None:
    within = (Ref.parse("doc:ojk:pojk:2024:40"),)

    assert SearchRequest("perizinan", documents=within).documents == within
    with pytest.raises(InvalidArgument, match="doc:ojk:pojk:2024:40#pasal-5 is a part"):
        SearchRequest("perizinan", documents=(Ref.parse("doc:ojk:pojk:2024:40#pasal-5"),))


def test_links_are_asked_both_ways_of_every_type_by_default() -> None:
    request = LinksRequest()

    assert (request.direction, request.types, request.limit) == (Direction.BOTH, frozenset(), 8)
    with pytest.raises(InvalidArgument):
        LinksRequest(limit=MAX_LIMIT + 1)


def test_a_link_from_a_passage_names_what_it_names() -> None:
    link = Link(
        LinkType.NAMES,
        source=Ref.parse("release:ojk:siaran-pers:2025:ojk-terbitkan-pojk-40#p-2"),
        target=Ref.parse("doc:ojk:pojk:2024:40"),
    )

    assert (link.effective_on, link.confidence) == (None, None)


def test_a_links_confidence_is_between_zero_and_one() -> None:
    with pytest.raises(ValueError, match="confidence 1.5"):
        Link(LinkType.AMENDS, Ref.parse("doc:a:b"), Ref.parse("doc:c:d"), confidence=1.5)
