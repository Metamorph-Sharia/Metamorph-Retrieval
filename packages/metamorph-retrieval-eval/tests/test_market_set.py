"""The market's question set stays readable, and keeps covering what M1 promised: every market tool, each journey
phase, and 40 to 60 cases."""

from collections import Counter
from pathlib import Path

from metamorph_retrieval_eval.cases import Phase, cases_from_jsonl

MARKET_SET = Path(__file__).resolve().parents[3] / "eval" / "market" / "cases.jsonl"
MARKET_TOOLS = {"search_documents", "read", "follow_links", "find_series", "get_observations", "find_companies",
                "industry_context"}


def test_the_market_set_reads_and_covers_every_tool_and_phase() -> None:
    cases = cases_from_jsonl(MARKET_SET.read_text(encoding="utf-8"))

    assert 40 <= len(cases) <= 60
    assert set(Counter(case.tool for case in cases)) == MARKET_TOOLS
    assert {case.phase for case in cases} == set(Phase)
