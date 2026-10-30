import pytest

from metamorph_market_retrieval.domain.names import NameMatch, name_match, normalised, rank_by_name
from metamorph_market_retrieval.domain.standing import standing_on


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("PT Dana Syariah Indonesia", "dana syariah indonesia"),
        ("PT. Investree Radhika Jaya, Tbk", "investree radhika jaya"),
        ("Danai.id", "danai id"),
        ("PT Bank Syariah Indonesia (Persero) Tbk", "bank syariah indonesia"),
    ],
)
def test_a_name_is_compared_without_case_punctuation_or_legal_form(name: str, expected: str) -> None:
    assert normalised(name) == expected


def test_a_name_matches_as_written_ignoring_case_first() -> None:
    match = name_match("ALAMI", ["PT Alami Fintek Sharia", "ALAMI", "Alami"])

    assert match is not None and match.kind is NameMatch.EXACT


def test_a_name_matches_once_normalised() -> None:
    match = name_match("Dana Syariah Indonesia", ["PT Dana Syariah Indonesia"])

    assert match is not None and match.kind is NameMatch.NORMALISED


def test_part_of_a_name_matches_less_the_less_of_the_name_it_covers() -> None:
    one_word = name_match("Investree", ["PT Investree Radhika Jaya"])
    two_words = name_match("Investree Radhika", ["PT Investree Radhika Jaya"])

    assert one_word is not None and one_word.kind is NameMatch.PARTIAL
    assert two_words is not None and two_words.score > one_word.score


def test_a_misspelt_name_matches_fuzzily_and_an_unrelated_one_not_at_all() -> None:
    fuzzy = name_match("Investre Radika Jaya", ["PT Investree Radhika Jaya"])

    assert fuzzy is not None and fuzzy.kind is NameMatch.FUZZY
    assert name_match("Kapital Boost", ["PT Dana Syariah Indonesia", "DANA SYARIAH"]) is None


def test_companies_are_ranked_by_their_best_name_and_ties_by_key() -> None:
    candidates = {
        "b": ["PT Danakoo Mitra Artha", "Danakoo"],
        "a": ["PT Dana Syariah Indonesia", "DANA SYARIAH"],
        "c": ["PT Duha Madani Syariah"],
    }

    ranked = rank_by_name("dana syariah", candidates)

    assert [key for key, _ in ranked] == ["a"]
    assert ranked[0][1].kind is NameMatch.EXACT  # "DANA SYARIAH", as listed


def test_ambiguous_names_return_every_candidate() -> None:
    ranked = rank_by_name("Syariah", {"a": ["PT Dana Syariah Indonesia"], "c": ["PT Duha Madani Syariah"]})

    assert [key for key, _ in ranked] == ["a", "c"]


@pytest.mark.parametrize(
    ("kinds", "status"),
    [({"license"}, "licensed"), ({"registration", "license"}, "licensed"), ({"registration"}, "registered"),
     ({"unknown"}, "listed")],
)
def test_a_companys_standing_on_an_edition_is_its_strongest_record_listed(kinds: set[str], status: str) -> None:
    assert standing_on(kinds) == status
