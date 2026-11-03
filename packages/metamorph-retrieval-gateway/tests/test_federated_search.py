"""A search several providers can answer goes to each of them, and their rankings are fused (reciprocal rank)."""

from dataclasses import replace

import pytest
from fakes import POJK_40, SearchingRegulations
from memory_provider import MemoryProvider
from retrieval_samples import regulation, release_passage, report_passage

from metamorph_retrieval_contract.errors import InvalidArgument, ProviderUnavailable
from metamorph_retrieval_contract.requests import SearchRequest
from metamorph_retrieval_gateway.application.gateway import Gateway

FATWA = replace(regulation(), ref=regulation().ref.__class__.parse("doc:dsnmui:fatwa:117"), kind="fatwa")
QUESTION = "pembiayaan syariah izin usaha"  # the memory provider finds its report and its release by these words


def refs(page) -> list[str]:  # noqa: ANN001 - a page of hits
    return [str(hit.evidence.ref) for hit in page.items]


def test_a_search_of_every_kind_fuses_the_providers_rankings() -> None:
    page = Gateway([MemoryProvider(), SearchingRegulations((regulation(), FATWA))]).search(SearchRequest(QUESTION))

    assert set(refs(page)) == {str(report_passage().ref), str(release_passage().ref), str(POJK_40), str(FATWA.ref)}
    assert [hit.rank for hit in page.items] == [1, 2, 3, 4]
    assert [hit.score for hit in page.items] == sorted((hit.score for hit in page.items), reverse=True)
    memory_first = refs(MemoryProvider().search(SearchRequest(QUESTION)))[0]
    assert set(refs(page)[:2]) == {memory_first, str(POJK_40)}  # each provider's first, ahead of either's second


def test_each_provider_is_asked_only_for_the_kinds_it_holds() -> None:
    regulations = SearchingRegulations()
    Gateway([MemoryProvider(), regulations]).search(SearchRequest(QUESTION, kinds=frozenset({"report", "regulation"})))

    assert [request.kinds for request in regulations.asked] == [frozenset({"regulation"})]


def test_a_search_one_provider_holds_is_that_providers_page() -> None:
    regulations = SearchingRegulations()
    page = Gateway([MemoryProvider(), regulations]).search(SearchRequest(QUESTION, kinds=frozenset({"regulation"}),
                                                                          cursor="0"))

    assert refs(page) == [str(POJK_40)]
    assert regulations.asked[0].cursor == "0"  # its own cursor, untouched


def test_a_provider_that_fails_leaves_the_others_answer_and_a_warning() -> None:
    failing = SearchingRegulations(fails=ProviderUnavailable("the regulation index is down"))
    page = Gateway([MemoryProvider(), failing]).search(SearchRequest(QUESTION))

    assert set(refs(page)) == {str(report_passage().ref), str(release_passage().ref)}
    assert page.warnings == ("regulation-search: the regulation index is down",)


def test_when_every_provider_fails_the_search_does() -> None:
    gateway = Gateway([SearchingRegulations(fails=RuntimeError("boom")),
                       _renamed_failing("fatwas", RuntimeError("boom"))])
    with pytest.raises(ProviderUnavailable, match="regulation-search failed"):
        gateway.search(SearchRequest(QUESTION))


def test_the_providers_warnings_say_whose_they_are() -> None:
    warned = SearchingRegulations(warnings=("sort: newest is not offered",))
    page = Gateway([MemoryProvider(), warned]).search(SearchRequest(QUESTION))

    assert page.warnings == ("regulation-search: sort: newest is not offered",)


def test_nothing_found_anywhere_is_an_empty_page() -> None:
    page = Gateway([MemoryProvider(), SearchingRegulations(())]).search(SearchRequest("tidak ada apa-apa"))

    assert page.items == () and page.empty_reason.value == "no_match"


def test_the_fused_ranking_pages_with_its_own_cursor() -> None:
    gateway = Gateway([MemoryProvider(), SearchingRegulations((regulation(), FATWA))])
    first = gateway.search(SearchRequest(QUESTION, limit=3))
    second = gateway.search(SearchRequest(QUESTION, limit=3, cursor=first.cursor))

    assert len(first.items) == 3 and first.cursor is not None
    assert [hit.rank for hit in second.items] == [4] and second.cursor is None
    assert set(refs(first) + refs(second)) == {str(report_passage().ref), str(release_passage().ref), str(POJK_40),
                                               str(FATWA.ref)}


def test_a_cursor_the_gateway_did_not_give_is_invalid() -> None:
    with pytest.raises(InvalidArgument):
        Gateway([MemoryProvider(), SearchingRegulations()]).search(SearchRequest(QUESTION, cursor="7"))


def _renamed_failing(name: str, error: Exception) -> SearchingRegulations:
    """A second regulation searcher under another name and namespace, failing too."""

    class Fatwas(SearchingRegulations):
        def manifest(self):  # noqa: ANN202
            return replace(super().manifest(), name=name, namespaces=frozenset({"fatwa"}))

    return Fatwas(fails=error)
