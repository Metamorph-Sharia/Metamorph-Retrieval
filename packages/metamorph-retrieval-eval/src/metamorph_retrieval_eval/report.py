"""A run's report: how many cases passed, and recall and MRR over the first k, for all, each tool and each phase.

Markdown for people; a dict (written as JSON) to compare runs, e.g. an index version against the active one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import fmean
from typing import Any

from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_eval.cases import Phase
from metamorph_retrieval_eval.scoring import Outcome


@dataclass(frozen=True)
class Summary:
    name: str
    cases: int
    passed: int
    recall: float | None  # mean over the cases that measure one
    mrr: float | None


@dataclass(frozen=True)
class Report:
    outcomes: tuple[Outcome, ...]
    unheld: tuple[Ref, ...] = field(default=())  # expected refs the provider doesn't hold

    def overall(self) -> Summary:
        return _summary("all", self.outcomes)

    def by_tool(self) -> list[Summary]:
        tools = sorted({outcome.case.tool for outcome in self.outcomes})
        return [_summary(tool, [o for o in self.outcomes if o.case.tool == tool]) for tool in tools]

    def by_phase(self) -> list[Summary]:
        """In the customer journey's order, from the market as a whole to a product's rules."""
        return [
            _summary(phase.value, chosen)
            for phase in Phase
            if (chosen := [o for o in self.outcomes if o.case.phase is phase])
        ]

    def failures(self) -> list[Outcome]:
        return [outcome for outcome in self.outcomes if not outcome.passed]


def render_markdown(report: Report, title: str) -> str:
    lines = [f"# {title}", "", *_table("Tool", [report.overall(), *report.by_tool()]), "", "## By phase", "",
             *_table("Phase", report.by_phase())]
    failures = report.failures()
    lines += ["", f"## Failures ({len(failures)})", ""]
    for outcome in failures:
        case = outcome.case
        lines.append(f"- **{case.id}** ({case.tool}, {case.phase.value}): {case.question}")
        lines.extend(f"  - {problem}" for problem in outcome.problems)
    if not failures:
        lines.append("None.")
    if report.unheld:
        lines += ["", "## Expected refs the provider doesn't hold", "", *(f"- {ref}" for ref in report.unheld)]
    return "\n".join(lines) + "\n"


def report_to_dict(report: Report) -> dict[str, Any]:
    return {
        "overall": _summary_dict(report.overall()),
        "by_tool": [_summary_dict(summary) for summary in report.by_tool()],
        "by_phase": [_summary_dict(summary) for summary in report.by_phase()],
        "cases": [
            {
                "id": outcome.case.id,
                "tool": outcome.case.tool,
                "phase": outcome.case.phase.value,
                "passed": outcome.passed,
                "recall": outcome.recall,
                "reciprocal_rank": outcome.reciprocal_rank,
                "problems": list(outcome.problems),
                "returned": [str(ref) for ref in outcome.result.refs],
            }
            for outcome in report.outcomes
        ],
        "unheld": [str(ref) for ref in report.unheld],
    }


def _summary(name: str, outcomes: Sequence[Outcome]) -> Summary:
    recalls = [outcome.recall for outcome in outcomes if outcome.recall is not None]
    ranks = [outcome.reciprocal_rank for outcome in outcomes if outcome.reciprocal_rank is not None]
    return Summary(
        name=name,
        cases=len(outcomes),
        passed=sum(1 for outcome in outcomes if outcome.passed),
        recall=fmean(recalls) if recalls else None,
        mrr=fmean(ranks) if ranks else None,
    )


def _table(first: str, summaries: Sequence[Summary]) -> list[str]:
    return [
        f"| {first} | Cases | Passed | Recall@k | MRR |",
        "|---|---|---|---|---|",
        *(f"| {s.name} | {s.cases} | {s.passed} | {_number(s.recall)} | {_number(s.mrr)} |" for s in summaries),
    ]


def _number(value: float | None) -> str:
    return "–" if value is None else f"{value:.2f}"


def _summary_dict(summary: Summary) -> dict[str, Any]:
    return {"name": summary.name, "cases": summary.cases, "passed": summary.passed, "recall": summary.recall,
            "mrr": summary.mrr}
