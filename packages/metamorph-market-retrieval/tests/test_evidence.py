from datetime import date

from market_samples import (
    ALAMI,
    INVESTREE,
    LPBBTI,
    LPBBTI_SYARIAH,
    M2,
    M2_FIGURES,
    PUBLISHED_AT,
    REVOCATION,
    REVOKED,
    ROADMAP,
    SEKI_1_1,
    SHARIA_BANKING,
    TARGETS,
)

from metamorph_market_retrieval.domain.evidence import (
    company_evidence,
    dataset_evidence,
    industry_evidence,
    passage_evidence,
    register_evidence,
    report_evidence,
    sector_evidence,
    series_evidence,
)
from metamorph_market_retrieval.domain.records import Passage
from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.evidence import Figures, LegalForce, Observation, PageSpan, Record, Text
from metamorph_retrieval_contract.refs import Ref


def test_a_company_is_cited_by_its_register_and_edition_and_qualified_by_its_standing() -> None:
    evidence = company_evidence(ALAMI)

    assert evidence.ref == Ref.parse("company:ojk:lpbbti:kep-21-d.05-2020")
    assert evidence.citation == (
        "OJK, Penyelenggara Layanan Pendanaan Bersama Berbasis Teknologi Informasi (fintech lending), edisi 2026-07-31"
    )
    assert (evidence.kind, evidence.title) == ("company", "PT Alami Fintek Sharia")
    assert evidence.legal_force is LegalForce.NONE
    assert (evidence.qualifiers.status, evidence.qualifiers.as_of) == ("licensed", date(2026, 7, 31))
    assert evidence.provenance.source_published_at == PUBLISHED_AT


def test_a_companys_record_names_its_register_and_lists_its_licences() -> None:
    assert isinstance((body := company_evidence(ALAMI).body), Record)

    assert body.fields["register"] == {"ref": "register:ojk:lpbbti"}
    assert body.fields["names"] == ["ALAMI", "Alami"]
    assert [licence["number"] for licence in body.fields["licences"]] == ["S-1/NB.213/2019", "KEP-21/D.05/2020"]
    assert body.fields["left_after"] is None


def test_a_companys_standing_on_a_past_edition_is_cited_by_that_edition() -> None:
    evidence = company_evidence(ALAMI, standing="registered", edition=date(2020, 3, 1))

    assert evidence.citation.endswith("edisi 2020-03-01")
    assert (evidence.qualifiers.status, evidence.qualifiers.as_of) == ("registered", date(2020, 3, 1))


def test_what_ojk_announced_about_a_company_is_named_by_passage() -> None:
    assert isinstance((body := company_evidence(INVESTREE, announcements=(REVOCATION,)).body), Record)

    assert body.fields["announcements"] == [{
        "ref": "release:ojk:siaran-pers:2024:ojk-cabut-izin-usaha-pt-investree-radhika-jaya#p-1",
        "citation": "Siaran Pers OJK SP-158/GKPB/OJK/X/2024, 21 Oktober 2024",
        "published_on": "2024-10-21",
    }]


def test_a_series_figures_are_labelled_by_its_frequency_and_qualified_by_the_sources_marks() -> None:
    evidence = series_evidence(M2, M2_FIGURES)

    assert evidence.body == Figures("Miliar Rp", "monthly", (
        Observation("2026-07", 10371597.498), Observation("2026-08", 10448066.078, provisional=True),
    ))
    assert evidence.citation == "Bank Indonesia, Statistik Ekonomi dan Keuangan Indonesia"
    assert (evidence.qualifiers.provisional, evidence.qualifiers.as_of) == (True, date(2026, 10, 15))
    assert evidence.url == SEKI_1_1.url


def test_a_series_without_figures_is_its_card_naming_its_dataset() -> None:
    assert isinstance((body := series_evidence(M2).body), Record)

    assert body.fields["dataset"] == {"ref": "dataset:bi:seki:tabel1_1"}
    assert (body.fields["first_period"], body.fields["last_period"]) == ("2010-01", "2026-08")


def test_a_dataset_names_its_register_regulations_and_reports_when_it_has_them() -> None:
    assert isinstance((body := dataset_evidence(SEKI_1_1).body), Record)

    assert (body.fields["register"], body.fields["governed_by"]) == (None, [])
    assert dataset_evidence(SEKI_1_1).title == "I.1. UANG BEREDAR DAN FAKTOR-FAKTOR YANG MEMPENGARUHINYA"


def test_an_industry_names_its_register_regulations_reports_and_datasets() -> None:
    evidence = industry_evidence(LPBBTI_SYARIAH)
    assert isinstance(evidence.body, Record)

    assert evidence.ref == Ref(
        "industry", "ojk:portal:layanan-pendanaan-bersama-berbasis-teknologi-informasi-lpbbti-syariah")
    assert evidence.body.fields["register"] == {"ref": "register:ojk:lpbbti"}
    assert evidence.body.fields["governed_by"] == [{"ref": "doc:ojk:pojk:2024:40"}, {"ref": "doc:ojk:seojk:2025:19"}]
    assert evidence.body.fields["reports"][1] == {"ref": "report:ojk:roadmap:2023:lpbbti"}
    assert evidence.body.fields["datasets"] == [{"ref": "dataset:ojk:portal:lpbbti_syariah_profilentitas"}]


def test_a_sector_names_its_industries_by_their_refs() -> None:
    evidence = sector_evidence(SHARIA_BANKING)
    assert isinstance(evidence.body, Record)

    assert (evidence.ref, evidence.title) == (Ref.parse("sector:sharia-banking"), "Perbankan Syariah")
    assert evidence.body.fields["industries"][0] == {"ref": "industry:ojk:portal:bank-umum-syariah"}
    assert evidence.body.fields["name_en"] == "Sharia banking"


def test_a_report_passage_is_cited_with_its_pages() -> None:
    evidence = passage_evidence(TARGETS)

    assert evidence.ref == Ref.parse("report:ojk:roadmap:2023:lpbbti#p-43")
    assert evidence.citation == f"{ROADMAP.citation}, hlm. 61–62"
    assert evidence.body == Text("Peningkatan Pembiayaan kepada Sektor Produktif dan UMKM…", PageSpan(61, 62))
    assert (evidence.kind, evidence.published_on) == ("report", date(2023, 11, 10))


def test_a_release_passage_has_no_pages_and_is_cited_as_the_release() -> None:
    evidence = passage_evidence(REVOKED)

    assert evidence.citation == "Siaran Pers OJK SP-158/GKPB/OJK/X/2024, 21 Oktober 2024"
    assert evidence.body == Text("Otoritas Jasa Keuangan (OJK) … mencabut izin usaha PT Investree…")


def test_a_passage_read_with_its_neighbours_spans_their_words_and_pages() -> None:
    before = Passage(ROADMAP, "p-42", 42, "pengembangan ekosistem…", 60, 61)

    evidence = passage_evidence(TARGETS, neighbours=(before,))

    assert evidence.ref == Ref.parse("report:ojk:roadmap:2023:lpbbti#p-43")
    assert evidence.body == Text("pengembangan ekosistem…\n\nPeningkatan Pembiayaan kepada Sektor Produktif dan UMKM…",
                                 PageSpan(60, 62))
    assert evidence.citation.endswith("hlm. 60–62")



def test_a_report_and_a_register_are_cards_of_their_own() -> None:
    report, register = report_evidence(ROADMAP), register_evidence(LPBBTI)
    assert isinstance(report.body, Record) and isinstance(register.body, Record)

    assert (report.ref, report.body.fields["pages"], report.body.fields["passages"]) == (
        Ref.parse("report:ojk:roadmap:2023:lpbbti"), 84, 59)
    assert register.body.fields["governed_by"] == [{"ref": "doc:ojk:pojk:2024:40"}, {"ref": "doc:ojk:seojk:2025:19"}]
    assert register.citation == "OJK, " + LPBBTI.name


def test_all_market_evidence_has_no_legal_force_and_is_readable_on_the_wire() -> None:
    every = [company_evidence(ALAMI), company_evidence(INVESTREE, announcements=(REVOCATION,)),
             series_evidence(M2, M2_FIGURES), series_evidence(M2), dataset_evidence(SEKI_1_1),
             industry_evidence(LPBBTI_SYARIAH),
             sector_evidence(SHARIA_BANKING), passage_evidence(TARGETS), passage_evidence(REVOKED),
             report_evidence(ROADMAP), register_evidence(LPBBTI)]

    for evidence in every:
        assert evidence.legal_force is LegalForce.NONE
        assert codec.evidence_from_dict(codec.to_dict(evidence)) == evidence
