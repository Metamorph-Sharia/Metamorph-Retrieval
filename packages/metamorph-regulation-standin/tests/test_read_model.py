"""The read model's contract, held by both models: in memory, and over PostgreSQL."""

from standin_samples import ARTICLE_5_1, FATWA_117, POJK_40, PUBLISHED_AT, RULING

from metamorph_regulation_standin.application.ports import RegulationReadModel


def test_the_newest_publish(read_model: RegulationReadModel) -> None:
    assert read_model.published_at() == PUBLISHED_AT


def test_documents_are_those_published_among_the_ids_asked(read_model: RegulationReadModel) -> None:
    found = read_model.documents([FATWA_117.id, "ojk:pojk:2099:1", POJK_40.id])

    assert sorted(found, key=lambda document: document.id) == [FATWA_117, POJK_40]


def test_units_are_those_published_among_the_keys_asked(read_model: RegulationReadModel) -> None:
    found = read_model.units([(POJK_40.id, "pasal-5/ayat-1"), (POJK_40.id, "pasal-99"),
                              (FATWA_117.id, "diktum-kedua/angka-1")])

    assert sorted(found, key=lambda unit: unit.address) == [RULING, ARTICLE_5_1]


def test_nothing_asked_is_nothing_found(read_model: RegulationReadModel) -> None:
    assert (read_model.documents([]), read_model.units([])) == ([], [])
