"""The regulation sets stay readable, broad, and apart: a holdout that shares a case with an open set checks nothing."""

from pathlib import Path

from metamorph_retrieval_eval.cases import Case, cases_from_jsonl

SETS = Path(__file__).resolve().parents[3] / "eval" / "regulation"
INSTRUMENT_KINDS = 9


def cases_in(name: str) -> tuple[Case, ...]:
    return cases_from_jsonl((SETS / name).read_text(encoding="utf-8"))


def kind_of(case: Case) -> str:
    return ":".join(str(case.expect.refs[0]).split(":")[1:3])


def test_the_drawn_sets_hold_a_hundred_cases_of_many_kinds() -> None:
    drawn = cases_in("corpus.jsonl") + cases_in("holdout.jsonl")

    assert len(drawn) >= 100
    assert len({kind_of(case) for case in drawn}) >= INSTRUMENT_KINDS


def test_the_holdout_shares_nothing_with_the_open_sets() -> None:
    holdout = cases_in("holdout.jsonl")
    held_refs = {case.expect.refs[0] for case in holdout}
    held_questions = {case.question for case in holdout}

    for name in ("corpus.jsonl", "cases.jsonl"):
        open_set = cases_in(name)
        assert not held_refs & {ref for case in open_set for ref in case.expect.refs}
        assert not held_questions & {case.question for case in open_set}
