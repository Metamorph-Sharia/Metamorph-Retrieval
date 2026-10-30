from dataclasses import replace

import pytest

from metamorph_retrieval_contract.evidence import Observation
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_eval.cases import Case, Expectation, Figure, Match, Phase
from metamorph_retrieval_eval.scoring import Result, judge, matches

R = Ref.parse
P43 = R("report:ojk:roadmap:2023:lpbbti#p-43")
P44 = R("report:ojk:roadmap:2023:lpbbti#p-44")
P47 = R("report:ojk:roadmap:2023:lpbbti#p-47")
OTHER = [R(f"release:ojk:siaran-pers:2025:x#p-{n}") for n in range(1, 10)]
M2 = R("series:bi:seki:tabel1_1:monthly:row=1")


def case(expect: Expectation) -> Case:
    return Case("c", Phase.INDUSTRY, "?", "search_documents", {"query": "?"}, expect, basis="test")


def test_an_expected_document_is_found_by_any_of_its_passages() -> None:
    assert matches(R("report:ojk:roadmap:2023:lpbbti"), P43)
    assert matches(P43, P43)
    assert not matches(P43, P44)
    assert not matches(P43, R("report:ojk:roadmap:2023:lpbbti"))  # a passage isn't found by its whole


def test_all_means_every_expected_ref_in_the_first_k() -> None:
    expect = Expectation(refs=(P43, P47), match=Match.ALL, k=3)

    found = judge(case(expect), Result(refs=(OTHER[0], P43, P47)))
    late = judge(case(expect), Result(refs=(OTHER[0], P43, OTHER[1], P47)))

    assert (found.passed, found.recall, found.reciprocal_rank) == (True, 1.0, 0.5)
    assert (late.passed, late.recall) == (False, 0.5)
    assert late.problems == ("not in the first 3: report:ojk:roadmap:2023:lpbbti#p-47",)


def test_any_means_one_expected_ref_in_the_first_k() -> None:
    expect = Expectation(refs=(P43, P44, P47), match=Match.ANY, k=8)

    outcome = judge(case(expect), Result(refs=(*OTHER[:3], P44)))

    assert (outcome.passed, outcome.reciprocal_rank) == (True, 0.25)
    assert outcome.recall == pytest.approx(1 / 3)


def test_nothing_expected_in_the_first_k_has_no_rank() -> None:
    outcome = judge(case(Expectation(refs=(P43,), match=Match.ANY)), Result(refs=tuple(OTHER)))

    assert (outcome.passed, outcome.recall, outcome.reciprocal_rank) == (False, 0.0, 0.0)
    assert outcome.problems == ("none in the first 8 of: report:ojk:roadmap:2023:lpbbti#p-43",)


def test_exact_means_these_items_and_no_others_in_any_order() -> None:
    expect = Expectation(refs=(P43, P44), match=Match.EXACT)

    assert judge(case(expect), Result(refs=(P44, P43))).passed
    outcome = judge(case(expect), Result(refs=(P43, P47)))
    assert outcome.problems == (
        "missing: report:ojk:roadmap:2023:lpbbti#p-44",
        "not expected: report:ojk:roadmap:2023:lpbbti#p-47",
    )


def test_the_items_must_name_what_is_expected() -> None:
    industry = R("industry:ojk:portal:lpbbti-syariah")
    expect = Expectation(refs=(industry,), names=(R("doc:ojk:pojk:2024:40"), R("register:ojk:lpbbti")))

    outcome = judge(case(expect), Result(refs=(industry,), names=frozenset({R("doc:ojk:pojk:2024:40")})))

    assert outcome.problems == ("doesn't name: register:ojk:lpbbti",)


def test_figures_are_checked_by_value_and_by_provisional_mark_when_given() -> None:
    expect = Expectation(refs=(M2,), match=Match.EXACT, figures=(
        Figure(M2, "2026-07", 10371597.498, provisional=False),
        Figure(M2, "2026-08", 10448066.078, provisional=True),
        Figure(M2, "2026-09", 1.0),
    ))
    figures = ((M2, Observation("2026-07", 10371597.498)), (M2, Observation("2026-08", 10448066.0, provisional=False)))

    outcome = judge(case(expect), Result(refs=(M2,), figures=figures))

    assert outcome.problems == (
        "series:bi:seki:tabel1_1:monthly:row=1 2026-08: 10448066.0, not 10448066.078",
        "series:bi:seki:tabel1_1:monthly:row=1 2026-08: not marked provisional",
        "series:bi:seki:tabel1_1:monthly:row=1 2026-09: no figure",
    )


def test_an_expected_error_passes_only_when_that_error_is_raised() -> None:
    expect = Expectation(error="unknown_ref")

    assert judge(case(expect), Result(error="unknown_ref")).passed
    assert judge(case(expect), Result(refs=(P43,))).problems == ("expected unknown_ref, got a result",)
    other = judge(case(expect), Result(error="invalid_argument"))
    assert other.problems == ("expected unknown_ref, got invalid_argument",)


def test_an_unexpected_error_fails_the_case_with_its_message() -> None:
    outcome = judge(case(Expectation(refs=(P43,))), Result(error="unknown_tool", message="no tool find_series"))

    assert (outcome.passed, outcome.recall, outcome.reciprocal_rank) == (False, 0.0, 0.0)
    assert outcome.problems == ("raised unknown_tool: no tool find_series",)


def test_an_error_case_has_no_ranking_to_measure() -> None:
    outcome = judge(case(Expectation(error="unknown_ref")), Result(error="unknown_ref"))

    assert (outcome.recall, outcome.reciprocal_rank) == (None, None)


def test_an_exact_tools_outcome_is_measured_like_a_search() -> None:
    expect = Expectation(refs=(P43, P44), match=Match.EXACT)

    outcome = judge(replace(case(expect), tool="find_companies"), Result(refs=(P44, P43)))

    assert (outcome.recall, outcome.reciprocal_rank) == (1.0, 1.0)
