import pytest

from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_eval.cases import Case, Expectation, Phase
from metamorph_retrieval_eval.report import Report, Summary, render_markdown, report_to_dict
from metamorph_retrieval_eval.scoring import Outcome, Result

P43 = Ref.parse("report:ojk:roadmap:2023:lpbbti#p-43")


def outcome(case_id: str, tool: str, phase: Phase, passed: bool, recall: float | None, rr: float | None,
            problems: tuple[str, ...] = ()) -> Outcome:
    case = Case(case_id, phase, f"question {case_id}?", tool, {}, Expectation(refs=(P43,)), basis="test")
    return Outcome(case, Result(), passed, recall, rr, problems)


REPORT = Report(
    outcomes=(
        outcome("a", "search_documents", Phase.INDUSTRY, True, 1.0, 1.0),
        outcome("b", "search_documents", Phase.COMPLIANCE, False, 0.5, 0.25, ("not in the first 8: x",)),
        outcome("c", "find_companies", Phase.INDUSTRY, True, 1.0, 1.0),
        outcome("d", "read", Phase.INDUSTRY, True, None, None),
    ),
    unheld=(Ref.parse("report:ojk:lpksi:1999#p-1"),),
)


def test_the_report_sums_up_every_case_then_each_tool_and_each_phase() -> None:
    assert REPORT.overall() == Summary(
        "all", cases=4, passed=3, recall=pytest.approx(2.5 / 3), mrr=pytest.approx(2.25 / 3)
    )
    assert REPORT.by_tool() == [
        Summary("find_companies", 1, 1, 1.0, 1.0),
        Summary("read", 1, 1, None, None),
        Summary("search_documents", 2, 1, 0.75, 0.625),
    ]
    assert [(summary.name, summary.cases) for summary in REPORT.by_phase()] == [("industry", 3), ("compliance", 1)]


def test_the_markdown_shows_the_tables_each_failure_and_the_refs_not_held() -> None:
    text = render_markdown(REPORT, title="Market, 2026-10-30")

    assert text.startswith("# Market, 2026-10-30\n")
    assert "| all | 4 | 3 | 0.83 | 0.75 |" in text
    assert "| read | 1 | 1 | – | – |" in text
    assert "- **b** (search_documents, compliance): question b?\n  - not in the first 8: x" in text
    assert "- report:ojk:lpksi:1999#p-1" in text


def test_the_json_form_keeps_each_cases_numbers_for_comparing_runs() -> None:
    data = report_to_dict(REPORT)

    assert data["overall"] == {"name": "all", "cases": 4, "passed": 3, "recall": pytest.approx(2.5 / 3),
                               "mrr": pytest.approx(0.75)}
    assert data["cases"][1] == {"id": "b", "tool": "search_documents", "phase": "compliance", "passed": False,
                                "recall": 0.5, "reciprocal_rank": 0.25, "problems": ["not in the first 8: x"],
                                "returned": []}
    assert data["unheld"] == ["report:ojk:lpksi:1999#p-1"]
