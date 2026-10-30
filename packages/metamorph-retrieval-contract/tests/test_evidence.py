from dataclasses import replace

import pytest
from retrieval_samples import release_passage

from metamorph_retrieval_contract.evidence import EmptyReason, Hit, MatchedBy, Page, PageSpan, Text


def test_a_describe_card_is_the_evidence_without_its_body() -> None:
    evidence = release_passage()

    card = evidence.card()

    assert card.body is None
    assert card == replace(evidence, body=None)


def test_nothing_found_is_an_empty_page_that_says_why() -> None:
    page = Page.empty(EmptyReason.FILTERS_EXCLUDE_ALL)

    assert page.items == ()
    assert page.empty_reason is EmptyReason.FILTERS_EXCLUDE_ALL


def test_an_empty_page_without_a_reason_is_refused() -> None:
    with pytest.raises(ValueError, match="an empty page says why"):
        Page(items=())


def test_a_page_with_items_has_no_empty_reason() -> None:
    hit = Hit(release_passage(), rank=1, score=0.8, matched_by=frozenset({MatchedBy.WORDS}))

    with pytest.raises(ValueError, match="only an empty page"):
        Page(items=(hit,), empty_reason=EmptyReason.NO_MATCH)


def test_a_hit_is_ranked_from_one_and_says_how_it_matched() -> None:
    with pytest.raises(ValueError, match="rank"):
        Hit(release_passage(), rank=0, score=0.8, matched_by=frozenset({MatchedBy.WORDS}))
    with pytest.raises(ValueError, match="matched_by"):
        Hit(release_passage(), rank=1, score=0.8, matched_by=frozenset())


def test_pages_of_a_text_run_forwards() -> None:
    assert Text("…", pages=PageSpan(31, 32)).pages == PageSpan(31, 32)
    with pytest.raises(ValueError, match="page 32 to 31"):
        PageSpan(32, 31)
