"""Evidence as the providers will return it, from the platform's own examples (published-market-schema.md)."""

from datetime import UTC, date, datetime

from metamorph_retrieval_contract.evidence import (
    Evidence,
    Figures,
    LegalForce,
    Observation,
    PageSpan,
    Provenance,
    Qualifiers,
    Record,
    Text,
)
from metamorph_retrieval_contract.refs import Ref

PUBLISHED_AT = datetime(2026, 10, 29, 7, 45, tzinfo=UTC)


def provenance(provider: str = "market") -> Provenance:
    return Provenance(provider=provider, index_version="market-2026-10-30.1", source_published_at=PUBLISHED_AT)


def release_passage() -> Evidence:
    return Evidence(
        ref=Ref.parse("release:ojk:siaran-pers:2026:ojk-cabut-izin-usaha-pt-porto-ventura-kapital#p-1"),
        kind="release",
        citation="Siaran Pers OJK SP 188/DKPU/OJK/X/2026, 8 Oktober 2026",
        title="OJK Cabut Izin Usaha PT Porto Ventura Kapital",
        legal_force=LegalForce.NONE,
        qualifiers=Qualifiers(),
        published_on=date(2026, 10, 8),
        url="https://ojk.go.id/id/berita-dan-kegiatan/siaran-pers/Pages/sp-188.aspx",
        body=Text("Otoritas Jasa Keuangan mencabut izin usaha PT Porto Ventura Kapital…"),
        provenance=provenance(),
    )


def report_passage() -> Evidence:
    return Evidence(
        ref=Ref.parse("report:ojk:lpksi:2025#p-12"),
        kind="report",
        citation="Otoritas Jasa Keuangan, Laporan Perkembangan Keuangan Syariah Indonesia 2025",
        title="Laporan Perkembangan Keuangan Syariah Indonesia 2025",
        legal_force=LegalForce.NONE,
        qualifiers=Qualifiers(),
        published_on=date(2026, 5, 20),
        url=None,
        body=Text("Pembiayaan fintech lending syariah tumbuh…", pages=PageSpan(31, 32)),
        provenance=provenance(),
    )


def m2_series() -> Evidence:
    return Evidence(
        ref=Ref.parse("series:bi:seki:tabel1_1:monthly:row=1"),
        kind="series",
        citation="Bank Indonesia, Statistik Ekonomi dan Keuangan Indonesia, Tabel I.1",
        title="Uang Beredar Luas (M2)",
        legal_force=LegalForce.NONE,
        qualifiers=Qualifiers(provisional=True, as_of=date(2026, 10, 15)),
        published_on=None,
        url="https://www.bi.go.id/id/statistik/ekonomi-keuangan/seki/Default.aspx",
        body=Figures(
            unit="Miliar Rp",
            frequency="monthly",
            observations=(Observation("2026-07", 9512345.6), Observation("2026-08", 9601234.5, provisional=True)),
        ),
        provenance=provenance(),
    )


def company() -> Evidence:
    return Evidence(
        ref=Ref.parse("company:ojk:lpbbti:kep-49-d.05-2017"),
        kind="company",
        citation="OJK, Penyelenggara LPBBTI Berizin, Juli 2026",
        title="PT Fintech Bina Bangsa",
        legal_force=LegalForce.NONE,
        qualifiers=Qualifiers(status="licensed", as_of=date(2026, 7, 31)),
        published_on=None,
        url=None,
        body=Record({"register": "ojk:lpbbti", "business_type": "sharia", "first_listed": "2019-12-31"}),
        provenance=provenance(),
    )


def regulation() -> Evidence:
    return Evidence(
        ref=Ref.parse("doc:ojk:pojk:2024:40"),
        kind="regulation",
        citation="Peraturan Otoritas Jasa Keuangan Nomor 40 Tahun 2024",
        title="Layanan Pendanaan Bersama Berbasis Teknologi Informasi",
        legal_force=LegalForce.BINDING,
        qualifiers=Qualifiers(status="in_force", valid_from=date(2024, 12, 27)),
        published_on=date(2024, 12, 27),
        url=None,
        body=Text("Peraturan Otoritas Jasa Keuangan ini mengatur…"),
        provenance=provenance("regulation"),
    )
