"""Comparing two runs of one question set: a candidate (a new index version) against the active one.

The gate (retrieval-architecture.md §8): a candidate may be activated only if it passes at least as many cases and
recalls at least as much. Cases gained and lost are always listed, since a candidate no worse overall can still lose
a case that matters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TOLERANCE = 1e-9  # recall is a mean of fractions; equal runs may differ in the last digit


@dataclass(frozen=True)
class Comparison:
    active: dict[str, Any]
    candidate: dict[str, Any]
    gained: list[str]
    lost: list[str]

    @property
    def no_worse(self) -> bool:
        before, after = self.active["overall"], self.candidate["overall"]
        return after["passed"] >= before["passed"] and after["recall"] >= before["recall"] - TOLERANCE


def compare(active: dict[str, Any], candidate: dict[str, Any]) -> Comparison:
    before = {case["id"]: case["passed"] for case in active["cases"]}
    after = {case["id"]: case["passed"] for case in candidate["cases"]}
    return Comparison(active, candidate,
                      gained=[case for case, ok in after.items() if ok and not before.get(case, False)],
                      lost=[case for case, ok in before.items() if ok and not after.get(case, False)])


def render_comparison(comparison: Comparison, active_title: str, candidate_title: str) -> str:
    before = {row["name"]: row for row in [comparison.active["overall"], *comparison.active["by_tool"]]}
    after = {row["name"]: row for row in [comparison.candidate["overall"], *comparison.candidate["by_tool"]]}
    lines = [f"# {active_title} → {candidate_title}", "", "| Tool | Passed | Recall@k | MRR |", "|---|---|---|---|"]
    for name, row in after.items():
        old = before.get(name, {"cases": row["cases"], "passed": 0, "recall": None, "mrr": None})
        lines.append(f"| {name} | {old['passed']} of {old['cases']} → {row['passed']} of {row['cases']} | "
                     f"{_number(old['recall'])} → {_number(row['recall'])} | "
                     f"{_number(old['mrr'])} → {_number(row['mrr'])} |")
    verdict = ("**No worse:** {a} → {c} may be activated." if comparison.no_worse
               else "**Worse:** keep {a}; {c} passes fewer cases or recalls less.")
    lines += ["", verdict.format(a=active_title, c=candidate_title), "",
              f"Gained: {', '.join(comparison.gained) or 'none'}", "",
              f"Lost: {', '.join(comparison.lost) or 'none'}", ""]
    return "\n".join(lines)


def _number(value: float | None) -> str:
    return "–" if value is None else f"{value:.2f}"
