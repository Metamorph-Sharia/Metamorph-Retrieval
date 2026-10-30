import pytest
from standin_samples import ARTICLE_5_1, FATWA_117, POJK_40, PUBLISHED_AT, RULING

from metamorph_regulation_standin.domain.evidence import (
    document_evidence,
    legal_force_of,
    provision_label,
    unit_evidence,
)
from metamorph_retrieval_contract.evidence import LegalForce, PageSpan, Provenance, Qualifiers, Record, Text
from metamorph_retrieval_contract.refs import Ref


@pytest.mark.parametrize(
    ("address", "label"),
    [
        ("pasal-5", "Pasal 5"),
        ("pasal-5/ayat-1/huruf-a", "Pasal 5 ayat (1) huruf a"),
        ("pasal-1/angka-3/huruf-b", "Pasal 1 angka 3 huruf b"),
        ("pasal-2/huruf-i", "Pasal 2 huruf i"),
        ("penjelasan/pasal-5/ayat-1", "Penjelasan Pasal 5 ayat (1)"),
        ("pasal-i/pasal-115", "Pasal I Pasal 115"),
        ("bab-ii/bagian-kesatu", "BAB II Bagian Kesatu"),
        ("lampiran-i/bab-ii", "Lampiran I BAB II"),
        ("lampiran", "Lampiran"),
        ("menimbang/huruf-a", "Menimbang huruf a"),
        ("romawi-ii/angka-3", "II angka 3"),
        ("diktum-kedua/angka-1", "Diktum Kedua angka 1"),
    ],
)
def test_a_provisions_label_is_read_from_its_address(address: str, label: str) -> None:
    assert provision_label(address) == label


@pytest.mark.parametrize(
    ("kind", "force"),
    [("law", LegalForce.BINDING), ("regulation", LegalForce.BINDING), ("implementing_rule", LegalForce.BINDING),
     ("fatwa", LegalForce.SHARIA), ("guideline", LegalForce.SHARIA), ("explanatory", LegalForce.EXPLANATORY)],
)
def test_legal_force_comes_from_the_documents_kind(kind: str, force: LegalForce) -> None:
    assert legal_force_of(kind) is force


def test_a_kind_without_a_legal_force_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError, match="kind 'decree' has no legal force yet"):
        legal_force_of("decree")


def test_a_document_is_its_card_and_its_facts() -> None:
    evidence = document_evidence(POJK_40)

    assert (evidence.ref, evidence.kind, evidence.citation, evidence.legal_force) == (
        Ref.parse("doc:ojk:pojk:2024:40"), "regulation", "POJK 40 Tahun 2024", LegalForce.BINDING)
    assert evidence.qualifiers == Qualifiers(status="partly_revoked", valid_from=POJK_40.effective_on,
                                             as_of=POJK_40.status_as_of)
    assert evidence.published_on == POJK_40.promulgated_on
    assert evidence.body == Record({"issuer": "ojk", "family": "pojk", "number": "40", "year": 2024,
                                    "enacted_on": "2024-12-20", "promulgated_on": "2024-12-27",
                                    "effective_on": "2024-12-27", "aliases": ["POJK 40/2024"]})
    assert evidence.provenance == Provenance("regulation-standin", "published-sql", PUBLISHED_AT)


def test_a_provision_is_its_wording_cited_by_its_address() -> None:
    evidence = unit_evidence(ARTICLE_5_1)

    assert evidence.ref == Ref.parse("doc:ojk:pojk:2024:40#pasal-5/ayat-1")
    assert evidence.citation == "POJK 40 Tahun 2024, Pasal 5 ayat (1)"
    assert evidence.body == Text(ARTICLE_5_1.wording, PageSpan(6, 6))


def test_a_provision_carries_its_own_validity_and_review() -> None:
    evidence = unit_evidence(RULING)

    assert evidence.legal_force is LegalForce.SHARIA
    assert evidence.qualifiers == Qualifiers(status="unknown", valid_to=RULING.valid_to, under_review=True)
    assert evidence.body == Text(RULING.wording, None)
    assert evidence.citation == f"{FATWA_117.citation}, Diktum Kedua angka 1"
