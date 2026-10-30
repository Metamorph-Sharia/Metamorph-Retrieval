import hashlib

from market_samples import LPBBTI_SYARIAH, REVOKED, ROADMAP, SEKI_1_1, SHARIA_BANKING, TARGETS

from metamorph_market_retrieval.domain.fusion import RRF_K, reciprocal_rank_fusion
from metamorph_market_retrieval.domain.indexing import dataset_unit, industry_unit, passage_unit, sector_unit
from metamorph_retrieval_contract.refs import Ref


def test_fusion_rewards_what_both_rankings_put_high() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "d", "a"]])

    assert [key for key, _ in fused] == ["b", "a", "d", "c"]
    assert fused[0][1] == 1 / (RRF_K + 2) + 1 / (RRF_K + 1)


def test_fusion_breaks_ties_by_key_so_the_same_call_gives_the_same_order() -> None:
    assert [key for key, _ in reciprocal_rank_fusion([["z"], ["a"]])] == ["a", "z"]


def test_one_ranking_alone_keeps_its_order() -> None:
    assert [key for key, _ in reciprocal_rank_fusion([["c", "a", "b"], []])] == ["c", "a", "b"]


def test_a_report_passage_is_indexed_under_its_citation_and_pages() -> None:
    unit = passage_unit(TARGETS)

    assert unit.ref == Ref.parse("report:ojk:roadmap:2023:lpbbti#p-43")
    assert (unit.kind, unit.document, unit.issuer, unit.published_on) == (
        "report", Ref.parse("report:ojk:roadmap:2023:lpbbti"), "OJK", ROADMAP.published_on)
    assert unit.text == f"{ROADMAP.citation}, hlm. 61–62\n{TARGETS.text}"


def test_a_release_passage_is_indexed_under_its_citation_and_title_which_name_its_subject() -> None:
    unit = passage_unit(REVOKED)

    assert unit.text == ("Siaran Pers OJK SP-158/GKPB/OJK/X/2024, 21 Oktober 2024: Siaran Pers: OJK Cabut Izin Usaha "
                         f"PT Investree Radhika Jaya\n{REVOKED.text}")


def test_a_dataset_is_indexed_as_a_card_naming_what_it_measures() -> None:
    unit = dataset_unit(SEKI_1_1)

    assert (unit.ref, unit.kind, unit.document, unit.issuer) == (
        Ref.parse("dataset:bi:seki:tabel1_1"), "dataset", None, "bi")
    assert unit.text == ("I.1. UANG BEREDAR DAN FAKTOR-FAKTOR YANG MEMPENGARUHINYA\n"
                         "I. UANG DAN BANK; Bank Indonesia, Statistik Ekonomi dan Keuangan Indonesia; "
                         "2010-01 – 2026-08")


def test_a_units_hash_is_its_texts_so_unchanged_text_is_never_embedded_twice() -> None:
    unit = passage_unit(TARGETS)

    assert unit.text_hash == hashlib.sha256(unit.text.encode()).hexdigest()


def test_an_industry_is_indexed_by_its_name_and_where_it_comes_from() -> None:
    unit = industry_unit(LPBBTI_SYARIAH)

    assert (unit.ref, unit.kind, unit.issuer) == (
        Ref.parse("industry:ojk:portal:layanan-pendanaan-bersama-berbasis-teknologi-informasi-lpbbti-syariah"),
        "industry", "ojk")
    assert unit.text == f"{LPBBTI_SYARIAH.name}\nojk:portal"


def test_a_sector_is_indexed_by_its_names_in_both_languages() -> None:
    unit = sector_unit(SHARIA_BANKING)

    assert (unit.ref, unit.kind, unit.text) == (Ref.parse("sector:sharia-banking"), "sector",
                                                "Perbankan Syariah\nSharia banking")
