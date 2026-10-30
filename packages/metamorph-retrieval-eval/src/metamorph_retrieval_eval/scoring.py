"""Judging one case: did the call return the evidence expected, early enough, naming and counting what it should?

Recall and reciprocal rank are measured over the first k items (over every item for an exact tool), so a search and
an exact tool are reported on one scale. An expected whole document (a ref without an address) is found by any of
its passages: some questions are answered anywhere in a report.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from metamorph_retrieval_contract.evidence import Observation
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_eval.cases import Case, Expectation, Figure, Match


@dataclass(frozen=True)
class Result:
    """What a call returned, as the judge reads it."""

    refs: tuple[Ref, ...] = ()  # the items returned, in order
    names: frozenset[Ref] = frozenset()  # what the items name in their fields
    figures: tuple[tuple[Ref, Observation], ...] = ()
    error: str | None = None  # the error code the call raised
    message: str = ""


@dataclass(frozen=True)
class Outcome:
    case: Case
    result: Result
    passed: bool
    recall: float | None  # None for a case that expects an error
    reciprocal_rank: float | None
    problems: tuple[str, ...] = field(default=())


def matches(expected: Ref, returned: Ref) -> bool:
    return returned == expected or (expected.address is None and returned.whole() == expected)


def judge(case: Case, result: Result) -> Outcome:
    expect = case.expect
    if expect.error is not None:
        return Outcome(case, result, result.error == expect.error, None, None, _error_problems(expect.error, result))
    if result.error is not None:
        return Outcome(case, result, False, 0.0, 0.0, (f"raised {result.error}: {result.message}",))
    considered = result.refs if expect.match is Match.EXACT else result.refs[: expect.k]
    problems = (
        *_ref_problems(expect, considered),
        *_name_problems(expect.names, result.names),
        *_figure_problems(expect.figures, result.figures),
    )
    recall, rank = _recall(expect.refs, considered), _reciprocal_rank(expect.refs, considered)
    return Outcome(case, result, not problems, recall, rank, problems)


def _error_problems(expected: str, result: Result) -> tuple[str, ...]:
    if result.error is None:
        return (f"expected {expected}, got a result",)
    return () if result.error == expected else (f"expected {expected}, got {result.error}",)


def _ref_problems(expect: Expectation, considered: Sequence[Ref]) -> tuple[str, ...]:
    missing = [ref for ref in expect.refs if not _found(ref, considered)]
    if expect.match is Match.EXACT:
        extra = [ref for ref in considered if not any(matches(expected, ref) for expected in expect.refs)]
        return (*_listed("missing", missing), *_listed("not expected", extra))
    if expect.match is Match.ALL:
        return _listed(f"not in the first {expect.k}", missing)
    if len(missing) == len(expect.refs):
        return _listed(f"none in the first {expect.k} of", missing)
    return ()


def _name_problems(expected: Sequence[Ref], named: frozenset[Ref]) -> tuple[str, ...]:
    return _listed("doesn't name", [ref for ref in expected if not _found(ref, named)])


def _figure_problems(expected: Sequence[Figure], figures: Sequence[tuple[Ref, Observation]]) -> list[str]:
    problems = []
    for figure in expected:
        where = f"{figure.ref} {figure.period}"
        found = [obs for ref, obs in figures if ref == figure.ref and obs.period == figure.period]
        if not found:
            problems.append(f"{where}: no figure")
            continue
        observation = found[0]
        if not math.isclose(observation.value, figure.value, rel_tol=1e-9, abs_tol=1e-9):
            problems.append(f"{where}: {observation.value}, not {figure.value}")
        if figure.provisional is not None and observation.provisional != figure.provisional:
            problems.append(f"{where}: {'not marked' if figure.provisional else 'marked'} provisional")
    return problems


def _recall(expected: Sequence[Ref], considered: Sequence[Ref]) -> float:
    return sum(1 for ref in expected if _found(ref, considered)) / len(expected)


def _reciprocal_rank(expected: Sequence[Ref], considered: Sequence[Ref]) -> float:
    for rank, returned in enumerate(considered, start=1):
        if any(matches(ref, returned) for ref in expected):
            return 1 / rank
    return 0.0


def _found(expected: Ref, returned: Sequence[Ref] | frozenset[Ref]) -> bool:
    return any(matches(expected, ref) for ref in returned)


def _listed(what: str, refs: Sequence[Ref]) -> tuple[str, ...]:
    return (f"{what}: {', '.join(str(ref) for ref in refs)}",) if refs else ()
