import json

import pytest

from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_eval.cases import CaseProblems, Figure, Match, Phase, cases_from_jsonl


def line(**overrides: object) -> str:
    case = {
        "id": "companies-licensed-sharia",
        "phase": "industry",
        "question": "Which sharia P2P lenders does OJK license today?",
        "tool": "find_companies",
        "arguments": {"register": "ojk:lpbbti", "business_type": "sharia", "status": "licensed"},
        "expect": {"refs": ["company:ojk:lpbbti:kep-21-d.05-2020"], "match": "exact"},
        "basis": "published_market.company, 2026-10-30",
    }
    case.update(overrides)
    return json.dumps(case)


def test_a_case_reads_as_its_question_call_and_expected_evidence() -> None:
    (case,) = cases_from_jsonl(line())

    assert (case.id, case.phase, case.tool) == ("companies-licensed-sharia", Phase.INDUSTRY, "find_companies")
    assert case.arguments == {"register": "ojk:lpbbti", "business_type": "sharia", "status": "licensed"}
    assert case.expect.refs == (Ref.parse("company:ojk:lpbbti:kep-21-d.05-2020"),)
    assert case.expect.match is Match.EXACT


def test_what_a_case_leaves_out_is_a_search_in_the_first_eight_naming_nothing() -> None:
    (case,) = cases_from_jsonl(line(expect={"refs": ["report:ojk:roadmap:2023:lpbbti#p-43"]}))

    assert (case.expect.match, case.expect.k, case.expect.names, case.expect.figures, case.expect.error) == (
        Match.ALL, 8, (), (), None,
    )


def test_figures_name_a_series_period_and_value() -> None:
    expect = {
        "refs": ["series:bi:seki:tabel1_1:monthly:row=1"],
        "match": "exact",
        "figures": [{"ref": "series:bi:seki:tabel1_1:monthly:row=1", "period": "2026-08", "value": 10448066.078,
                     "provisional": True}],
    }

    (case,) = cases_from_jsonl(line(expect=expect))

    assert case.expect.figures == (
        Figure(Ref.parse("series:bi:seki:tabel1_1:monthly:row=1"), "2026-08", 10448066.078, provisional=True),
    )


def test_blank_lines_and_comments_are_skipped() -> None:
    text = "\n".join(["# industry questions", "", line()])

    assert len(cases_from_jsonl(text)) == 1


def test_every_problem_in_a_file_is_reported_with_its_line() -> None:
    text = "\n".join([
        line(),
        line(phase="retail"),
        "{not json",
        line(),  # its id repeats line 1's
        line(id="figures-not-returned", expect={"refs": ["series:a:b"], "figures": [
            {"ref": "series:c:d", "period": "2026-08", "value": 1}]}),
        line(id="neither", expect={}),
        line(id="bad-ref", expect={"refs": ["Company OJK"]}),
    ])

    with pytest.raises(CaseProblems) as caught:
        cases_from_jsonl(text)

    assert [problem.split(":")[0] for problem in caught.value.problems] == [
        "line 2", "line 3", "line 4", "line 5", "line 6", "line 7",
    ]
    assert "line 4: id companies-licensed-sharia is also on line 1" in caught.value.problems
    assert "line 5: figures: series:c:d is not among the expected refs" in caught.value.problems
    assert "line 6: expect: name the refs expected, or the error" in caught.value.problems
