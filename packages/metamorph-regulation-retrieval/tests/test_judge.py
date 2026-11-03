import json

from metamorph_regulation_retrieval.indexing.judge import Score, _found, load_cases, worse_than


def test_a_small_difference_is_inside_the_tolerance() -> None:
    active = Score(0.60, 0.50, 40)
    new = Score(0.59, 0.49, 40)

    assert worse_than(new, active, 0.02) == []


def test_a_step_beyond_the_tolerance_is_worse() -> None:
    active = Score(0.60, 0.50, 40)
    new = Score(0.55, 0.45, 40)

    assert worse_than(new, active, 0.02) == ["document@5", "clause in set"]


def test_an_expected_parent_matches_its_children() -> None:
    rows = [("doc:a", "pasal-5/ayat-1"), ("doc:b", "pasal-1")]

    assert _found({"document_id": "doc:a", "address": "pasal-5"}, ["doc:a"], rows) is True
    assert _found({"document_id": "doc:a", "address": "pasal-6"}, ["doc:a"], rows) is False


def test_document_level_evidence_needs_only_the_document() -> None:
    assert _found({"document_id": "doc:a"}, ["doc:a"], []) is True
    assert _found({"document_id": "doc:a"}, ["doc:b"], []) is False


def test_the_judge_reads_the_question_set_metamorph_eval_runs(tmp_path) -> None:  # noqa: ANN001
    cases = tmp_path / "cases.jsonl"
    cases.write_text("\n".join(json.dumps(case) for case in [
        {"id": "a", "tool": "search_documents", "arguments": {"query": "batas pendanaan", "in_force_on": "2026-10-23"},
         "expect": {"refs": ["doc:ojk:pojk:2024:40#pasal-137/ayat-3", "doc:dsnmui:fatwa:117"], "match": "all"}},
        {"id": "b", "tool": "read", "arguments": {"ref": "doc:ojk:pojk:2024:40"}, "expect": {"refs": []}},
    ]))

    assert load_cases(cases) == [{"question": "batas pendanaan", "expected": [
        {"document_id": "ojk:pojk:2024:40", "address": "pasal-137/ayat-3"},
        {"document_id": "dsnmui:fatwa:117", "address": None}]}]
