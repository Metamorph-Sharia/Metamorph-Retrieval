"""Comparing a candidate index version's run with the active one's: the gate before activating (§8)."""

import json

import pytest

from metamorph_retrieval_eval.cli import main
from metamorph_retrieval_eval.compare import compare, render_comparison


def run(passed: dict[str, bool], recall: float, mrr: float = 0.5) -> dict:
    tools = {"find_series": [case for case in passed if case.startswith("series")],
             "search_documents": [case for case in passed if case.startswith("search")]}
    return {
        "overall": {"name": "all", "cases": len(passed), "passed": sum(passed.values()), "recall": recall, "mrr": mrr},
        "by_tool": [{"name": tool, "cases": len(ids), "passed": sum(passed[case] for case in ids), "recall": recall,
                     "mrr": mrr} for tool, ids in tools.items()],
        "cases": [{"id": case, "passed": ok} for case, ok in passed.items()],
    }


ACTIVE = run({"series-a": True, "search-a": False, "search-b": False}, recall=0.3)


def test_a_candidate_passing_more_with_no_less_recall_is_no_worse() -> None:
    candidate = run({"series-a": True, "search-a": True, "search-b": False}, recall=0.6)

    comparison = compare(ACTIVE, candidate)

    assert comparison.no_worse
    assert (comparison.gained, comparison.lost) == (["search-a"], [])


def test_a_candidate_losing_recall_is_worse_even_passing_as_many() -> None:
    candidate = run({"series-a": True, "search-a": False, "search-b": False}, recall=0.2)

    assert not compare(ACTIVE, candidate).no_worse


def test_a_candidate_passing_fewer_is_worse_and_names_the_cases_it_lost() -> None:
    active = run({"series-a": True, "search-a": False, "search-b": True}, recall=0.3)
    candidate = run({"series-a": False, "search-a": True, "search-b": False}, recall=0.4)
    comparison = compare(active, candidate)

    assert not comparison.no_worse
    assert (comparison.gained, comparison.lost) == (["search-a"], ["series-a", "search-b"])


def test_the_comparison_reads_as_a_table_per_tool() -> None:
    candidate = run({"series-a": True, "search-a": True, "search-b": False}, recall=0.6)

    text = render_comparison(compare(ACTIVE, candidate), "words only", "bge-m3")

    assert "| all | 1 of 3 → 2 of 3 | 0.30 → 0.60 | 0.50 → 0.50 |" in text
    assert "| search_documents | 0 of 2 → 1 of 2 |" in text
    assert "**No worse:** words only → bge-m3 may be activated." in text
    assert "Gained: search-a" in text


@pytest.mark.parametrize(("recall", "status"), [(0.6, 0), (0.1, 3)])
def test_compare_exits_zero_only_when_the_candidate_may_be_activated(tmp_path, recall: float, status: int) -> None:  # noqa: ANN001
    active, candidate = tmp_path / "active.json", tmp_path / "candidate.json"
    active.write_text(json.dumps(ACTIVE), encoding="utf-8")
    candidate.write_text(json.dumps(run({"series-a": True, "search-a": True, "search-b": False}, recall)),
                         encoding="utf-8")

    assert main(["compare", str(active), str(candidate), "--markdown", str(tmp_path / "out.md")]) == status
    assert (tmp_path / "out.md").read_text(encoding="utf-8").startswith("# ")
