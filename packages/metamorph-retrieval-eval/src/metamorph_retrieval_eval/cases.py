"""Evaluation cases: a question, the tool call that should answer it, and the evidence it should return.

A question set is a JSON Lines file, one case per line (`schemas/case.schema.json`); `#` starts a comment line.
The question is as a user would ask it, for the agent's evaluation; the call is the one a good agent would make,
so retrieval is judged on its own: "retrieval missed it" apart from "the agent asked badly".
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from importlib.resources import files
from typing import Any

from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import DEFAULT_LIMIT
from metamorph_retrieval_contract.schema import json_problems


class Phase(StrEnum):
    """The customer journey's phases, from the market as a whole to a product's rules."""

    MACRO = "macro"
    INDUSTRY = "industry"
    PRODUCT = "product"
    COMPLIANCE = "compliance"


class Match(StrEnum):
    EXACT = "exact"  # the items returned are the expected ones and no others: an exact tool
    ALL = "all"  # every expected ref is in the first k
    ANY = "any"  # at least one is: a broad question many passages answer


@dataclass(frozen=True)
class Figure:
    ref: Ref
    period: str
    value: float
    provisional: bool | None = None  # None: not checked


@dataclass(frozen=True)
class Expectation:
    refs: tuple[Ref, ...] = ()
    match: Match = Match.ALL
    k: int = DEFAULT_LIMIT
    names: tuple[Ref, ...] = ()
    figures: tuple[Figure, ...] = ()
    error: str | None = None  # an error code the call should raise instead


@dataclass(frozen=True)
class Case:
    id: str
    phase: Phase
    question: str
    tool: str
    arguments: Mapping[str, Any]
    expect: Expectation
    basis: str = field(compare=False)


class CaseProblems(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def cases_from_jsonl(text: str) -> tuple[Case, ...]:
    """Every case in the file, or CaseProblems listing every problem found, each with its line."""
    cases: list[Case] = []
    problems: list[str] = []
    first_line: dict[str, int] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        found = _case_problems(raw)
        if found:
            problems.extend(f"line {number}: {problem}" for problem in found)
            continue
        case = _case(json.loads(raw))
        if case.id in first_line:
            problems.append(f"line {number}: id {case.id} is also on line {first_line[case.id]}")
            continue
        first_line[case.id] = number
        cases.append(case)
    if problems:
        raise CaseProblems(problems)
    return tuple(cases)


def _case_problems(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"not JSON: {exc}"]
    found = json_problems(data, _schema())
    if found:
        return found
    expect = data["expect"]
    if not expect.get("refs") and "error" not in expect:
        return ["expect: name the refs expected, or the error"]
    refs = set(expect.get("refs", ()))
    return [
        f"figures: {figure['ref']} is not among the expected refs"
        for figure in expect.get("figures", ())
        if figure["ref"] not in refs
    ]


def _case(data: Mapping[str, Any]) -> Case:
    expect = data["expect"]
    return Case(
        id=data["id"],
        phase=Phase(data["phase"]),
        question=data["question"],
        tool=data["tool"],
        arguments=data["arguments"],
        expect=Expectation(
            refs=tuple(Ref.parse(ref) for ref in expect.get("refs", ())),
            match=Match(expect.get("match", Match.ALL)),
            k=expect.get("k", DEFAULT_LIMIT),
            names=tuple(Ref.parse(ref) for ref in expect.get("names", ())),
            figures=tuple(
                Figure(Ref.parse(figure["ref"]), figure["period"], figure["value"], figure.get("provisional"))
                for figure in expect.get("figures", ())
            ),
            error=expect.get("error"),
        ),
        basis=data["basis"],
    )


@cache
def _schema() -> dict[str, Any]:
    return json.loads(files("metamorph_retrieval_eval").joinpath("schemas", "case.schema.json").read_text("utf-8"))
