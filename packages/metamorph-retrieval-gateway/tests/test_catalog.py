"""The agent's catalog: the contract's operations as tools, then every provider's own, each checked and recorded."""

from dataclasses import replace

import pytest
from fakes import POJK_40, Industries, Recorded, Regulations
from memory_provider import MANIFEST, MemoryProvider
from retrieval_samples import regulation, report_passage

from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.errors import CapabilityMissing, InvalidArgument, UnknownRef, UnknownTool
from metamorph_retrieval_contract.provider import ToolSpec
from metamorph_retrieval_gateway.application.calls import TRACE, Call, TraceContext
from metamorph_retrieval_gateway.application.catalog import Catalog
from metamorph_retrieval_gateway.application.gateway import Gateway

TRACED = TraceContext("4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7")


class Broken:
    def record(self, call: Call) -> None:
        raise OSError("disk full")


def catalog(*providers: object, **options: object) -> Catalog:
    providers = providers or (MemoryProvider(), Regulations(), Industries())
    return Catalog(Gateway(providers), **options)  # type: ignore[arg-type]


def test_the_contracts_operations_come_first_then_the_providers_tools() -> None:
    names = [tool.name for tool in catalog().tools()]

    assert names == ["search_documents", "read", "follow_links", "count", "industry_context"]


def test_an_operation_no_provider_offers_isnt_listed() -> None:
    assert [tool.name for tool in catalog(Regulations(), Industries()).tools()] == ["read", "industry_context"]


def test_the_search_tool_says_which_kinds_it_searches() -> None:
    (search,) = [tool for tool in catalog().tools() if tool.name == "search_documents"]

    assert "Searches the passages of releases and reports" in search.description


def test_a_provider_tool_named_like_an_operation_is_refused() -> None:
    shadowing = ToolSpec("read", "0.1", "Reads.", {"type": "object"}, {"type": "object"})

    with pytest.raises(ValueError, match="read: a provider's tool can't take an operation's name"):
        catalog(MemoryProvider(manifest=replace(MANIFEST, tools=(shadowing,))))


def test_read_answers_the_evidence() -> None:
    assert catalog().run("read", {"ref": str(POJK_40)}) == codec.to_dict(regulation())


def test_follow_links_answers_a_page_of_links() -> None:
    page = codec.links_from_dict(catalog().run("follow_links", {"ref": str(POJK_40), "direction": "incoming"}))

    assert [link.target for link in page.items] == [POJK_40]


def test_search_documents_answers_a_page_of_hits() -> None:
    page = codec.hits_from_dict(catalog().run("search_documents", {"query": "fintech syariah", "limit": 3}))

    assert page.items[0].evidence.ref == report_passage().ref


def test_a_providers_tool_answers_as_the_provider_does() -> None:
    assert catalog().run("count", {"kind": "release"}) == {"count": 1}


def test_arguments_are_checked_against_the_tools_schema_and_every_problem_told() -> None:
    with pytest.raises(InvalidArgument) as caught:
        catalog().run("follow_links", {"direction": "sideways", "limit": 40})

    assert caught.value.message == (
        "follow_links: (value): 'ref' is a required property; direction: 'sideways' is not one of ['outgoing', "
        "'incoming', 'both']; limit: 40 is greater than the maximum of 25")


def test_a_tool_not_in_the_catalog_names_those_that_are() -> None:
    with pytest.raises(UnknownTool, match="no tool get_provision; the tools are search_documents, read, "
                                          "follow_links, count, industry_context"):
        catalog().run("get_provision", {})


def test_an_answer_over_the_size_budget_is_refused_saying_how_to_ask_for_less() -> None:
    with pytest.raises(InvalidArgument, match=r"read: the answer is [\d,]+ bytes, over the 200 one call may "
                                              "return; ask for less"):
        catalog(max_answer_bytes=200).run("read", {"ref": str(POJK_40)})


def test_each_call_is_recorded_with_what_came_back_and_the_agents_trace() -> None:
    log = Recorded()
    token = TRACE.set(TRACED)
    try:
        catalog(calls=log).run("search_documents", {"query": "fintech syariah"})
    finally:
        TRACE.reset(token)

    (call,) = log.calls
    assert (call.tool, call.arguments, call.trace) == ("search_documents", {"query": "fintech syariah"}, TRACED)
    assert call.refs == (str(report_passage().ref),)
    assert call.scores == (2.0,)
    assert call.index_versions == ("market-2026-10-30.1",)
    assert call.error is None and call.duration_ms >= 0


def test_a_failed_call_is_recorded_with_its_error_and_still_raised() -> None:
    log = Recorded()

    with pytest.raises(UnknownRef):
        catalog(calls=log).run("read", {"ref": "doc:ojk:pojk:1999:1"})

    (call,) = log.calls
    assert (call.error, call.message, call.refs) == ("unknown_ref", "regulation holds nothing under "
                                                                    "doc:ojk:pojk:1999:1", ())


def test_a_call_log_that_fails_never_fails_the_answer() -> None:
    assert catalog(calls=Broken()).run("count", {"kind": "report"}) == {"count": 1}


def test_an_operation_no_provider_offers_yet_is_missing_and_says_why() -> None:
    with pytest.raises(CapabilityMissing, match="no provider searches yet"):
        catalog(Regulations(), Industries()).run("search_documents", {"query": "pendanaan"})
