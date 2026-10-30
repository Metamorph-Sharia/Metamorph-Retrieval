from dataclasses import replace
from datetime import date

import pytest
from market_samples import LPBBTI_SYARIAH, M2
from memory_index import ConceptEmbedder, MemoryIndex
from memory_market import M1, QUASI_MONEY, MemoryMarket

from metamorph_market_retrieval.application.context import ContextQuery, IndustryContext
from metamorph_market_retrieval.application.search import Meaning
from metamorph_market_retrieval.application.statistics import (
    MAX_FIGURES,
    FindSeries,
    GetObservations,
    ObservationsQuery,
    SeriesQuery,
)
from metamorph_market_retrieval.domain.indexing import dataset_unit, industry_unit, sector_unit
from metamorph_market_retrieval.domain.records import ObservationRow
from metamorph_market_retrieval.domain.refs import industry_ref
from metamorph_retrieval_contract.errors import InvalidArgument, UnknownRef
from metamorph_retrieval_contract.evidence import EmptyReason, Figures, MatchedBy
from metamorph_retrieval_contract.refs import Ref

M2_REF = Ref.parse("series:bi:seki:tabel1_1:monthly:row=1")


def context(query: str):  # noqa: ANN201
    return IndustryContext(MemoryMarket()).run(ContextQuery(query))


def test_industry_context_ranks_sectors_and_industries_by_the_words_they_share_with_the_query() -> None:
    page = context("bank umum syariah")

    assert [hit.evidence.ref.namespace for hit in page.items] == ["industry", "sector", "industry"]
    assert page.items[0].evidence.title == "Bank Umum Syariah"


def test_a_sector_comes_before_an_industry_that_matches_as_well() -> None:
    page = context("perbankan syariah")

    assert page.items[0].evidence.ref == Ref.parse("sector:sharia-banking")


def test_a_sector_is_also_found_by_its_english_name() -> None:
    assert context("sharia banking").items[0].evidence.ref == Ref.parse("sector:sharia-banking")


def test_a_query_no_industry_shares_a_word_with_is_no_match() -> None:
    assert context("asuransi jiwa").empty_reason is EmptyReason.NO_MATCH


def test_find_series_finds_the_dataset_then_its_series_by_label() -> None:
    page = FindSeries(MemoryMarket()).run(SeriesQuery("uang beredar luas M2"))

    hit = page.items[0]
    assert (hit.evidence.ref, hit.rank) == (M2_REF, 1)
    assert hit.evidence.body.fields["dataset"] == {"ref": "dataset:bi:seki:tabel1_1"}


def test_find_series_ranks_by_the_words_of_the_dataset_and_the_label_together() -> None:
    page = FindSeries(MemoryMarket()).run(SeriesQuery("uang dan bank sempit"))

    found = [hit.evidence.ref.id for hit in page.items]
    assert found[0] == M1.id and found.index(M1.id) < found.index(M2.id)  # all four words, then three
    assert page.items[0].score == 1.0


def test_of_rows_holding_every_word_the_one_the_query_names_comes_before_its_sub_rows() -> None:
    page = FindSeries(MemoryMarket()).run(SeriesQuery("uang beredar luas M2"))

    found = [hit.evidence.ref.id for hit in page.items]
    assert found[0] == M2.id and found.index(M2.id) < found.index(QUASI_MONEY.id)


def test_a_page_shows_a_few_series_of_each_dataset_before_more_of_one() -> None:
    page = FindSeries(MemoryMarket(), per_dataset=1).run(SeriesQuery("uang beredar"))

    assert [hit.evidence.ref.id.split(":monthly")[0] for hit in page.items] == [
        "bi:seki:tabel1_1", "bi:seki:tabel1_0", "bi:seki:tabel1_1", "bi:seki:tabel1_1"]


def test_find_series_with_no_dataset_holding_the_words_is_no_match() -> None:
    assert FindSeries(MemoryMarket()).run(SeriesQuery("asuransi jiwa")).empty_reason is EmptyReason.NO_MATCH


def test_find_series_refuses_a_frequency_it_doesnt_know() -> None:
    with pytest.raises(InvalidArgument, match="frequency 'weekly': monthly, quarterly, semiannual or annual"):
        SeriesQuery("inflasi", frequency="weekly")


def test_observations_come_between_two_periods_as_the_source_gives_them() -> None:
    page = GetObservations(MemoryMarket()).run(ObservationsQuery((M2_REF,), start="2026-08", end="2026-08"))

    (series,) = page.items
    assert isinstance(series.body, Figures)
    assert [(item.period, item.value, item.provisional) for item in series.body.observations] == [
        ("2026-08", 10448066.078, True)
    ]


def test_an_unknown_series_is_named() -> None:
    unknown = Ref.parse("series:bi:seki:tabel1_1:monthly:row=999")

    with pytest.raises(UnknownRef, match="series:bi:seki:tabel1_1:monthly:row=999"):
        GetObservations(MemoryMarket()).run(ObservationsQuery((M2_REF, unknown)))


def test_without_a_starting_period_only_the_newest_figures_come_and_the_page_says_so() -> None:
    market = MemoryMarket()
    market.figures[M2.id] = [ObservationRow(date(2000 + n // 12, n % 12 + 1, 1), float(n), False)
                             for n in range(MAX_FIGURES + 5)]

    (series,) = (page := GetObservations(market).run(ObservationsQuery((M2_REF,)))).items

    assert len(series.body.observations) == MAX_FIGURES
    assert series.body.observations[-1].value == MAX_FIGURES + 4
    assert page.warnings == (f"series:{M2.id}: only the newest {MAX_FIGURES} figures; give from for older ones",)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"series": ()}, "series: name one to 20"),
        ({"series": tuple(replace(M2_REF, id=f"x:{n}") for n in range(21))}, "series: name one to 20"),
        ({"series": (Ref.parse("dataset:bi:seki:tabel1_1"),)}, "dataset:bi:seki:tabel1_1 is not a series"),
        ({"series": (M2_REF,), "start": "2026-09", "end": "2026-08"}, "from 2026-09 is after to 2026-08"),
    ],
)
def test_an_observations_query_that_cant_be_answered_is_refused(arguments: dict, message: str) -> None:
    with pytest.raises(InvalidArgument, match=message):
        ObservationsQuery(**arguments)


def by_meaning() -> Meaning:
    market = MemoryMarket()
    embedder = ConceptEmbedder()
    units = [*map(dataset_unit, market.every_dataset()), *map(industry_unit, market.industries()),
             *map(sector_unit, market.sectors())]
    return Meaning(MemoryIndex(units, embedder), embedder, min_similarity=0.3)


def test_a_question_sharing_no_word_with_the_tables_finds_series_by_their_datasets_meaning() -> None:
    assert FindSeries(MemoryMarket()).run(SeriesQuery("money supply")).empty_reason is EmptyReason.NO_MATCH

    page = FindSeries(MemoryMarket(), meaning=by_meaning()).run(SeriesQuery("money supply"))

    assert page.items[0].evidence.ref.id.startswith(("bi:seki:tabel1_0:", "bi:seki:tabel1_1:"))  # money supply
    assert page.items[0].matched_by == {MatchedBy.SEMANTIC}
    assert page.items[0].evidence.provenance.index_version == "market-test.1"


def test_with_meaning_an_indonesian_question_ranks_as_before() -> None:
    plain = FindSeries(MemoryMarket()).run(SeriesQuery("uang beredar luas M2"))
    hybrid = FindSeries(MemoryMarket(), meaning=by_meaning()).run(SeriesQuery("uang beredar luas M2"))

    assert [hit.evidence.ref for hit in hybrid.items[:3]] == [hit.evidence.ref for hit in plain.items[:3]]
    assert hybrid.items[0].matched_by == {MatchedBy.WORDS, MatchedBy.SEMANTIC}


def test_an_industry_named_in_another_language_is_found_by_meaning() -> None:
    assert IndustryContext(MemoryMarket()).run(ContextQuery("lending")).empty_reason is EmptyReason.NO_MATCH

    page = IndustryContext(MemoryMarket(), meaning=by_meaning()).run(ContextQuery("lending"))

    assert page.items[0].evidence.ref == industry_ref(LPBBTI_SYARIAH.source, LPBBTI_SYARIAH.name)
    assert page.items[0].matched_by == {MatchedBy.SEMANTIC}


def test_with_meaning_an_industry_matched_by_words_still_comes_first() -> None:
    page = IndustryContext(MemoryMarket(), meaning=by_meaning()).run(ContextQuery("bank umum syariah"))

    assert page.items[0].evidence.ref.id == "ojk:portal:bank-umum-syariah"
    assert MatchedBy.WORDS in page.items[0].matched_by
