"""What every read model must do, in memory and over PostgreSQL alike: the port's promises, on the same records."""

from datetime import date

from market_samples import ALAMI, INVESTREE, LPBBTI, M2, PUBLISHED_AT, REVOCATION, ROADMAP, SEKI_1_1, SHARIA_BANKING
from memory_market import BANK_UMUM_SYARIAH, DANA_SYARIAH, EDITION_2020, M1, QUASI_MONEY, MemoryMarket

from metamorph_market_retrieval.application.ports import MarketReadModel
from metamorph_market_retrieval.domain.records import Mention
from metamorph_market_retrieval.domain.words import words

REVOCATION_ID = "ojk:siaran-pers:2024:ojk-cabut-izin-usaha-pt-investree-radhika-jaya"


def test_it_says_when_the_market_was_last_published(read_model: MarketReadModel) -> None:
    assert read_model.published_at() == PUBLISHED_AT


def test_companies_are_filtered_by_register_standing_and_business_type(read_model: MarketReadModel) -> None:
    assert {c.id for c in read_model.companies("ojk:lpbbti", "licensed", "sharia")} == {ALAMI.id, DANA_SYARIAH.id}
    assert [c.id for c in read_model.companies(None, "left", None)] == [INVESTREE.id]
    assert read_model.companies("ojk:none", None, None) == []


def test_a_company_comes_whole_with_its_register_and_licences(read_model: MarketReadModel) -> None:
    assert read_model.company(ALAMI.id) == ALAMI
    assert read_model.company("ojk:lpbbti:none") is None


def test_on_a_day_the_edition_current_then_lists_each_company_with_its_records_kinds(
    read_model: MarketReadModel,
) -> None:
    listed = {item.company.id: (item.edition, item.kinds)
              for item in read_model.listed_on("ojk:lpbbti", date(2020, 6, 30))}

    assert listed == {
        ALAMI.id: (EDITION_2020, frozenset({"license"})),
        DANA_SYARIAH.id: (EDITION_2020, frozenset({"registration"})),
        INVESTREE.id: (EDITION_2020, frozenset({"license"})),
    }
    assert read_model.listed_on(None, date(2019, 1, 1)) == []
    assert {item.company.id for item in read_model.listed_on(None, date(2026, 10, 30))} == {ALAMI.id, DANA_SYARIAH.id}


def test_announcements_are_the_release_passages_naming_each_company(read_model: MarketReadModel) -> None:
    assert dict(read_model.announcements([INVESTREE.id, ALAMI.id])) == {INVESTREE.id: [REVOCATION]}


def test_registers_datasets_reports_and_releases_come_by_id(read_model: MarketReadModel) -> None:
    assert read_model.register(LPBBTI.id) == LPBBTI
    assert read_model.dataset(SEKI_1_1.id) == SEKI_1_1
    assert read_model.report(ROADMAP.id) == ROADMAP
    assert read_model.release(REVOCATION_ID).number == "SP-158/GKPB/OJK/X/2024"
    assert (read_model.register("x"), read_model.dataset("x"), read_model.report("x"), read_model.release("x")) == (
        None, None, None, None)


def test_industries_and_sectors_come_whole(read_model: MarketReadModel) -> None:
    assert BANK_UMUM_SYARIAH in read_model.industries()
    assert read_model.sectors() == [SHARIA_BANKING]


def test_datasets_and_then_their_series_are_found_by_their_words(read_model: MarketReadModel) -> None:
    datasets = read_model.datasets_matching(words("uang beredar"), None, 5)
    series = read_model.series_matching([SEKI_1_1.id], words("uang beredar luas m2"), None, 5)

    assert [dataset.id for dataset, _ in datasets] == [SEKI_1_1.id, "bi:seki:tabel1_0"]  # the fresher first
    assert [found.id for found, _ in series][:2] == [M2.id, QUASI_MONEY.id]
    assert read_model.datasets_matching(words("uang beredar"), "bps:table", 5) == []
    assert read_model.series_matching([SEKI_1_1.id], words("uang"), "annual", 5) == []
    assert read_model.datasets_matching(words("asuransi"), None, 5) == []


def test_a_matched_datasets_series_come_even_when_their_labels_hold_none_of_the_words(
    read_model: MarketReadModel,
) -> None:
    found = read_model.series_matching([SEKI_1_1.id], words("bank sempit"), None, 5)

    assert [series.id for series, _ in found][0] == M1.id  # "sempit" is M1's; "bank", only the dataset's group
    assert M2.id in [series.id for series, _ in found]


def test_a_datasets_series_come_best_first_up_to_the_limit(read_model: MarketReadModel) -> None:
    assert [s.id for s, _ in read_model.series_matching([SEKI_1_1.id], words("uang beredar luas"), None, 1)] == [M2.id]


def test_series_come_by_id_and_their_figures_between_two_days(read_model: MarketReadModel) -> None:
    assert read_model.series([M2.id, "none"]) == [M2]
    assert read_model.series([M1.id, M2.id]) == [M2, M1]  # by id
    figures = read_model.observations([M2.id], date(2026, 8, 1), date(2026, 8, 31))
    assert [(row.period, row.provisional) for row in figures[M2.id]] == [(date(2026, 8, 1), True)]
    assert [row.period for row in read_model.observations([M2.id], None, None)[M2.id]] == [date(2026, 7, 1),
                                                                                            date(2026, 8, 1)]


def test_a_passage_comes_with_its_neighbours_in_reading_order(read_model: MarketReadModel) -> None:
    assert [p.address for p in read_model.passages("report", ROADMAP.id, "p-43", 1)] == ["p-42", "p-43", "p-44"]
    assert [p.address for p in read_model.passages("report", ROADMAP.id, "p-43", 0)] == ["p-43"]
    assert read_model.passages("release", REVOCATION_ID, "p-1", 0)[0].page_start is None
    assert read_model.passages("report", ROADMAP.id, "p-999", 1) == []


def test_mentions_are_found_by_what_they_name_and_by_where_they_are(read_model: MarketReadModel) -> None:
    revoked_company = Mention("release", REVOCATION_ID, "p-1", "company", INVESTREE.id)
    revoked_rule = Mention("release", REVOCATION_ID, "p-1", "regulation", "ojk:pojk:2022:10")

    assert read_model.mentions_of("company", INVESTREE.id) == [revoked_company]
    assert read_model.mentions_in("release", REVOCATION_ID, None) == [revoked_company, revoked_rule]
    assert read_model.mentions_in("release", REVOCATION_ID, "p-2") == []
    assert read_model.mentions_of("regulation", "ojk:pojk:2024:40")[0].address == "p-44"


def test_every_passage_and_dataset_is_there_to_index(read_model: MarketReadModel) -> None:
    memory = MemoryMarket()

    passages = sorted(read_model.every_passage(), key=lambda passage: (passage.document.id, passage.ordinal))
    datasets = sorted(read_model.every_dataset(), key=lambda dataset: dataset.id)

    assert passages == sorted(memory.every_passage(), key=lambda passage: (passage.document.id, passage.ordinal))
    assert datasets == sorted(memory.every_dataset(), key=lambda dataset: dataset.id)
