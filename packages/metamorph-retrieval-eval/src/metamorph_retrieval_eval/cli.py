"""`metamorph-eval`: check a question set, run it against a provider, or compare two runs.

    metamorph-eval check eval/market/cases.jsonl
    metamorph-eval run eval/market/cases.jsonl --provider package.module:factory --markdown report.md --json report.json
    metamorph-eval compare active.json candidate.json      exits 0 only if the candidate may be activated

The provider is built by calling `factory()`; it is whatever the run is judging, a provider or, later, the gateway.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from metamorph_retrieval_contract.provider import RetrievalProvider
from metamorph_retrieval_eval.cases import Case, CaseProblems, Phase, cases_from_jsonl
from metamorph_retrieval_eval.compare import compare, render_comparison
from metamorph_retrieval_eval.report import Report, render_markdown, report_to_dict
from metamorph_retrieval_eval.runner import run, unheld

CHECKED, PROBLEMS, UNUSABLE, WORSE = 0, 1, 2, 3


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "check":
        return _check(args.cases)
    if args.command == "compare":
        return _compare(args)
    return _run(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="metamorph-eval", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check question sets and count their cases")
    check.add_argument("cases", nargs="+", type=Path)
    run_it = commands.add_parser("run", help="run a question set against a provider")
    run_it.add_argument("cases", type=Path)
    run_it.add_argument("--provider", required=True, help="module:factory, called with no arguments")
    run_it.add_argument("--title", default="Retrieval evaluation")
    run_it.add_argument("--markdown", type=Path, help="write the report here; stdout when left out")
    run_it.add_argument("--json", type=Path, help="also write the report as JSON, to compare runs")
    compare_runs = commands.add_parser("compare", help="compare a candidate's run with the active one's (JSON)")
    compare_runs.add_argument("active", type=Path)
    compare_runs.add_argument("candidate", type=Path)
    compare_runs.add_argument("--markdown", type=Path, help="write the comparison here; stdout when left out")
    return parser


def _check(paths: Sequence[Path]) -> int:
    status = CHECKED
    for path in paths:
        try:
            cases = cases_from_jsonl(path.read_text(encoding="utf-8"))
        except CaseProblems as found:
            print(f"{path}: {len(found.problems)} problems")
            print("\n".join(f"  {problem}" for problem in found.problems))
            status = PROBLEMS
            continue
        print(f"{path}: {len(cases)} cases")
        print(f"  by tool: {_counts(sorted(Counter(case.tool for case in cases).items()))}")
        phases = Counter(case.phase for case in cases)
        print(f"  by phase: {_counts([(phase.value, phases[phase]) for phase in Phase if phases[phase]])}")
    return status


def _run(args: argparse.Namespace) -> int:
    try:
        cases: Sequence[Case] = cases_from_jsonl(args.cases.read_text(encoding="utf-8"))
    except CaseProblems as found:
        print("\n".join(found.problems), file=sys.stderr)
        return PROBLEMS
    try:
        provider = _provider(args.provider)
    except (ImportError, AttributeError, ValueError) as exc:
        print(f"--provider {args.provider}: {exc}", file=sys.stderr)
        return UNUSABLE
    report = Report(outcomes=run(provider, cases), unheld=unheld(provider, cases))
    markdown = render_markdown(report, args.title)
    if args.markdown:
        args.markdown.write_text(markdown, encoding="utf-8")
    else:
        print(markdown, end="")
    if args.json:
        args.json.write_text(json.dumps(report_to_dict(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return CHECKED


def _compare(args: argparse.Namespace) -> int:
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in (args.active, args.candidate)]
    comparison = compare(*runs)
    text = render_comparison(comparison, args.active.stem, args.candidate.stem)
    if args.markdown:
        args.markdown.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return CHECKED if comparison.no_worse else WORSE


def _provider(spec: str) -> RetrievalProvider:
    module, _, factory = spec.partition(":")
    if not factory:
        raise ValueError("name it as module:factory")
    return getattr(importlib.import_module(module), factory)()


def _counts(pairs: Sequence[tuple[str, int]]) -> str:
    return ", ".join(f"{name} {count}" for name, count in pairs)
