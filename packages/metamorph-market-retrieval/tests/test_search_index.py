"""The search index's contract, held by both: in memory, and over PostgreSQL (full text in Indonesian, pgvector)."""

from datetime import UTC, date, datetime

import psycopg
import pytest
from market_samples import REVOKED, TARGETS
from memory_index import ConceptEmbedder

from metamorph_market_retrieval.adapters.index import PostgresIndexStore, PostgresSearchIndex
from metamorph_market_retrieval.adapters.postgres import PostgresMarketReadModel
from metamorph_market_retrieval.application.building import BuildIndex
from metamorph_market_retrieval.application.ports import UnitFilter
from metamorph_market_retrieval.domain.indexing import passage_unit
from metamorph_retrieval_contract.refs import Ref

PASSAGES = UnitFilter(frozenset({"report", "release"}))
TARGETS_REF = passage_unit(TARGETS).ref
REVOKED_REF = passage_unit(REVOKED).ref


def meaning(text: str) -> list[float]:
    return ConceptEmbedder().embed_queries([text])[0]


def test_words_find_a_passage_best_first(search_index) -> None:  # noqa: ANN001
    found = search_index.by_words("pembiayaan sektor produktif", PASSAGES, 10)

    assert found[0].ref == TARGETS_REF
    assert [match.score for match in found] == sorted((match.score for match in found), reverse=True)


def test_meaning_ranks_the_nearest_first_with_its_similarity(search_index) -> None:  # noqa: ANN001
    found = search_index.by_meaning(meaning("productive sector financing"), PASSAGES, 10)

    assert found[0].ref == TARGETS_REF
    assert 0 < found[0].score <= 1 and found[0].score > found[-1].score


@pytest.mark.parametrize(
    ("where", "kept"),
    [
        (UnitFilter(frozenset({"release"})), {REVOKED_REF}),
        (UnitFilter(frozenset({"report", "release"}), issuers=frozenset({"ojk"})), {TARGETS_REF, REVOKED_REF}),
        (UnitFilter(frozenset({"report", "release"}), published_from=date(2024, 1, 1)), {REVOKED_REF}),
        (UnitFilter(frozenset({"report", "release"}),
                    documents=frozenset({Ref.parse("report:ojk:roadmap:2023:lpbbti")})), {TARGETS_REF}),
        (UnitFilter(frozenset({"dataset"})), set()),
    ],
)
def test_both_rankings_keep_only_what_the_filter_keeps(search_index, where: UnitFilter, kept: set) -> None:  # noqa: ANN001
    query = "pembiayaan produktif izin usaha mencabut"
    by_words = {match.ref for match in search_index.by_words(query, where, 10)}
    by_meaning = {match.ref for match in search_index.by_meaning(meaning(query), where, 10)}

    assert kept <= by_words | by_meaning
    assert (by_words | by_meaning) & {TARGETS_REF, REVOKED_REF} <= kept


def test_dataset_cards_are_found_by_meaning(search_index) -> None:  # noqa: ANN001
    found = search_index.by_meaning(meaning("money supply"), UnitFilter(frozenset({"dataset"})), 3)

    assert Ref.parse("dataset:bi:seki:tabel1_1") in {match.ref for match in found}


@pytest.mark.database
def test_full_text_is_indonesian_so_a_word_finds_its_other_forms(indexed_database: str) -> None:
    with psycopg.connect(indexed_database) as connection:
        found = PostgresSearchIndex.active(connection).by_words("dibiayai", PASSAGES, 5)

    assert TARGETS_REF in {match.ref for match in found}  # dibiayai and pembiayaan share the stem biaya


@pytest.mark.database
def test_one_version_is_active_and_a_words_only_version_finds_nothing_by_meaning(indexed_database: str) -> None:
    with psycopg.connect(indexed_database) as connection:
        versions = PostgresIndexStore(connection).versions()
        words_only = PostgresSearchIndex.at(connection, versions[-1].version)

        assert [version.state for version in versions] == ["active", "ready"]
        assert (versions[0].model, versions[-1].model) == ("concepts-64", None)
        assert words_only.by_meaning(meaning("pembiayaan"), PASSAGES, 5) == []


@pytest.mark.database
def test_a_rebuild_reuses_every_cached_vector(indexed_database: str) -> None:
    with psycopg.connect(indexed_database, autocommit=True) as connection:
        built = BuildIndex(PostgresMarketReadModel(connection), PostgresIndexStore(connection), ConceptEmbedder(),
                           now=lambda: datetime(2026, 10, 31, tzinfo=UTC)).run()

    assert (built.embedded, built.cached) == (0, built.units)


def test_words_need_at_least_half_the_questions_words_so_one_shared_word_isnt_a_match(search_index) -> None:  # noqa: ANN001
    assert TARGETS_REF in {match.ref for match in search_index.by_words("pembiayaan produktif umkm", PASSAGES, 10)}
    assert search_index.by_words("cara membuat roti pembiayaan sourdough", PASSAGES, 10) == []
