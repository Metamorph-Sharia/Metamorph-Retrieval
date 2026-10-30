from collections.abc import Mapping
from typing import Any

from market_like import LPBBTI_SYARIAH, MarketLike
from memory_provider import POJK_40
from retrieval_samples import m2_series, release_passage, report_passage

from metamorph_retrieval_contract.provider import JSON
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_eval.cases import Case, Expectation, Figure, Match, Phase
from metamorph_retrieval_eval.runner import call, run, unheld

R = Ref.parse


def case(tool: str, arguments: dict[str, Any], expect: Expectation | None = None) -> Case:
    return Case("c", Phase.INDUSTRY, "?", tool, arguments, expect or Expectation(refs=(POJK_40,)), basis="test")


def test_search_documents_is_the_providers_search_and_returns_its_hits_in_order() -> None:
    result = call(MarketLike(), case("search_documents", {"query": "fintech syariah ojk"}))

    assert result.refs == (report_passage().ref, release_passage().ref)


def test_read_returns_the_one_piece_of_evidence() -> None:
    assert call(MarketLike(), case("read", {"ref": str(report_passage().ref)})).refs == (report_passage().ref,)


def test_follow_links_returns_the_other_end_of_each_link() -> None:
    arguments = {"ref": str(POJK_40), "direction": "incoming", "types": ["names"]}

    result = call(MarketLike(), case("follow_links", arguments))

    assert result.refs == (release_passage().ref,)


def test_a_tools_page_gives_its_items_figures_and_what_they_name() -> None:
    series = call(MarketLike(), case("find_series", {"query": "uang beredar"}))
    context = call(MarketLike(), case("industry_context", {"query": "sharia fintech lending"}))

    assert series.refs == (m2_series().ref,)
    assert [(str(ref), observation.period) for ref, observation in series.figures] == [
        ("series:bi:seki:tabel1_1:monthly:row=1", "2026-07"),
        ("series:bi:seki:tabel1_1:monthly:row=1", "2026-08"),
    ]
    assert context.refs == (LPBBTI_SYARIAH,)
    assert context.names == {R("register:ojk:lpbbti"), R("doc:ojk:pojk:2024:40"), R("doc:ojk:seojk:2025:19")}


def test_arguments_the_contract_refuses_are_the_agents_invalid_argument() -> None:
    result = call(MarketLike(), case("search_documents", {"query": "pembiayaan", "limit": 40}))

    assert result.error == "invalid_argument"
    assert "limit: 40 is greater than the maximum of 25" in result.message


def test_the_providers_errors_are_reported_by_their_code() -> None:
    assert call(MarketLike(), case("read", {"ref": "report:ojk:lpksi:1999#p-1"})).error == "unknown_ref"
    assert call(MarketLike(), case("find_nothing", {})).error == "unknown_tool"


def test_a_tool_output_that_isnt_a_page_of_evidence_is_the_providers_fault() -> None:
    result = call(MarketLike(), case("broken", {}))

    assert result.error == "malformed_output"
    assert "items[0]" in result.message


def test_a_provider_that_crashes_is_reported_and_the_run_goes_on() -> None:
    class Crashes(MarketLike):
        def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
            raise RuntimeError("index offline")

    outcomes = run(Crashes(), [case("find_series", {"query": "m2"}), case("read", {"ref": str(report_passage().ref)},
                                                                      Expectation(refs=(report_passage().ref,)))])

    assert [outcome.result.error for outcome in outcomes] == ["crashed", None]
    assert outcomes[0].result.message == "RuntimeError: index offline"
    assert outcomes[1].passed


def test_run_judges_every_case() -> None:
    expect = Expectation(refs=(m2_series().ref,), match=Match.EXACT,
                         figures=(Figure(m2_series().ref, "2026-08", 9601234.5, provisional=True),))

    (outcome,) = run(MarketLike(), [case("find_series", {"query": "uang beredar"}, expect)])

    assert outcome.passed, outcome.problems


def test_expected_refs_in_the_providers_namespaces_that_it_doesnt_hold_are_listed() -> None:
    stale = Expectation(refs=(report_passage().ref, R("report:ojk:lpksi:1999#p-1"), POJK_40))

    assert unheld(MarketLike(), [case("search_documents", {"query": "x"}, stale)]) == (R("report:ojk:lpksi:1999#p-1"),)


def test_a_read_or_links_call_without_a_ref_is_the_agents_invalid_argument() -> None:
    assert call(MarketLike(), case("read", {})).error == "invalid_argument"
    assert call(MarketLike(), case("follow_links", {"direction": "incoming"})).message == "ref: say which ref"
