from metamorph_regulation_index.judge import Score, _found, worse_than


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
