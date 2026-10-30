import pytest

from metamorph_market_retrieval.domain.words import word_precision, word_score, words


def test_words_are_lower_case_runs_of_letters_and_digits_once_each() -> None:
    assert words("Uang Beredar Luas(M2), uang beredar") == ("uang", "beredar", "luas", "m2")


def test_a_text_scores_the_share_of_the_querys_words_it_holds() -> None:
    name = "Bank Perekonomian Rakyat (BPR) Syariah"

    assert word_score(words("BPR syariah"), name) == 1.0
    assert word_score(words("bank umum syariah"), name) == pytest.approx(2 / 3)
    assert word_score(words("asuransi"), name) == 0.0
    assert word_score((), name) == 0.0


def test_a_text_is_as_precise_as_the_share_of_its_words_the_query_holds() -> None:
    asked = words("uang beredar luas m2")

    assert word_precision(asked, "Uang Beredar Luas(M2)") == 1.0
    assert word_precision(asked, "Uang Beredar Luas(M2) › Uang Beredar Sempit (M1)") == pytest.approx(4 / 6)
    assert word_precision(asked, "") == 0.0
