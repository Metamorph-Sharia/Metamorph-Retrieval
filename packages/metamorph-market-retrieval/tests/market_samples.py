"""Records as the read model returns them, taken from published_market on 2026-10-30."""

from datetime import UTC, date, datetime

from metamorph_market_retrieval.domain.records import (
    Announcement,
    Company,
    Dataset,
    Industry,
    Licence,
    ObservationRow,
    Passage,
    Register,
    Release,
    Report,
    Sector,
    Series,
)

PUBLISHED_AT = datetime(2026, 10, 29, 9, 31, 21, tzinfo=UTC)

LPBBTI = Register(
    id="ojk:lpbbti",
    issuer="OJK",
    name="Penyelenggara Layanan Pendanaan Bersama Berbasis Teknologi Informasi (fintech lending)",
    newest_edition=date(2026, 7, 31),
    editions=70,
    governed_by=("ojk:pojk:2024:40", "ojk:seojk:2025:19"),
    reports=("ojk:roadmap:2023:lpbbti",),
    published_at=PUBLISHED_AT,
)

ALAMI = Company(
    id="ojk:lpbbti:kep-21-d.05-2020",
    register=LPBBTI,
    legal_name="PT Alami Fintek Sharia",
    names=("ALAMI", "Alami"),
    business_type="sharia",
    status="licensed",
    first_listed=date(2019, 12, 20),
    left_after=None,
    licences=(
        Licence("registration", "S-1/NB.213/2019", date(2019, 3, 1), date(2019, 12, 20), date(2020, 3, 1), False, None),
        Licence("license", "KEP-21/D.05/2020", date(2020, 4, 2), date(2020, 4, 30), date(2026, 7, 31), True, None),
    ),
    review_notes=(),
)

INVESTREE = Company(
    id="ojk:lpbbti:kep-45-d.05-2019",
    register=LPBBTI,
    legal_name="PT Investree Radhika Jaya",
    names=("Investree",),
    business_type="conventional",
    status="left",
    first_listed=date(2019, 12, 20),
    left_after=date(2024, 9, 27),
    licences=(Licence("license", "KEP-45/D.05/2019", date(2019, 5, 13), date(2019, 12, 20), date(2024, 9, 27), False,
                      date(2024, 9, 27)),),
    review_notes=(),
)

REVOCATION = Announcement(
    release="ojk:siaran-pers:2024:ojk-cabut-izin-usaha-pt-investree-radhika-jaya",
    address="p-1",
    citation="Siaran Pers OJK SP-158/GKPB/OJK/X/2024, 21 Oktober 2024",
    published_on=date(2024, 10, 21),
)

SEKI_1_1 = Dataset(
    id="bi:seki:tabel1_1",
    source="bi:seki",
    industry=None,
    group="I. UANG DAN BANK",
    metric="I.1. UANG BEREDAR DAN FAKTOR-FAKTOR YANG MEMPENGARUHINYA",
    register=None,
    governed_by=(),
    reports=(),
    series_count=82,
    first_period=date(2010, 1, 1),
    last_period=date(2026, 8, 1),
    updated=date(2026, 10, 15),
    url="https://www.bi.go.id/id/statistik/ekonomi-keuangan/seki/Default.aspx",
    citation="Bank Indonesia, Statistik Ekonomi dan Keuangan Indonesia",
    published_at=PUBLISHED_AT,
)

M2 = Series(
    id="bi:seki:tabel1_1:monthly:row=1",
    dataset=SEKI_1_1,
    label="UANG BEREDAR DAN FAKTOR-FAKTOR YANG MEMPENGARUHINYA: Uang Beredar Luas(M2)",
    unit="Miliar Rp",
    frequency="monthly",
    first_period=date(2010, 1, 1),
    last_period=date(2026, 8, 1),
    observations=200,
)

M2_FIGURES = (
    ObservationRow(date(2026, 7, 1), 10371597.498, provisional=False),
    ObservationRow(date(2026, 8, 1), 10448066.078, provisional=True),
)

LPBBTI_SYARIAH = Industry(
    source="ojk:portal",
    name="Layanan Pendanaan Bersama Berbasis Teknologi Informasi (LPBBTI) Syariah",
    register="ojk:lpbbti",
    governed_by=("ojk:pojk:2024:40", "ojk:seojk:2025:19"),
    reports=("ojk:lpksi:2025", "ojk:roadmap:2023:lpbbti"),
    datasets=("ojk:portal:lpbbti_syariah_profilentitas",),
    published_at=PUBLISHED_AT,
)

SHARIA_BANKING = Sector(
    id="sharia-banking",
    name="Perbankan Syariah",
    name_en="Sharia banking",
    industries=(("ojk:portal", "Bank Umum Syariah"), ("ojk:portal", "Bank Perekonomian Rakyat (BPR) Syariah")),
    registers=(),
    governed_by=("id:uu:2008:21",),
    reports=("ojk:roadmap:2023:rp3si",),
    datasets=("ojk:portal:bu_syariah_totalaset",),
    published_at=PUBLISHED_AT,
)

ROADMAP = Report(
    id="ojk:roadmap:2023:lpbbti",
    issuer="OJK",
    family="roadmap",
    edition="2023-2028",
    title="Roadmap Pengembangan dan Penguatan Layanan Pendanaan Bersama Berbasis Teknologi Informasi 2023-2028",
    published_on=date(2023, 11, 10),
    language="id",
    url="https://ojk.go.id/id/berita-dan-kegiatan/publikasi/Pages/roadmap-lpbbti.aspx",
    citation="Otoritas Jasa Keuangan, Roadmap Pengembangan dan Penguatan LPBBTI 2023-2028",
    pages=84,
    passages=59,
    method="text_layer",
    published_at=PUBLISHED_AT,
)

TARGETS = Passage(ROADMAP, "p-43", 43, "Peningkatan Pembiayaan kepada Sektor Produktif dan UMKM…", 61, 62)

REVOCATION_RELEASE = Release(
    id="ojk:siaran-pers:2024:ojk-cabut-izin-usaha-pt-investree-radhika-jaya",
    issuer="OJK",
    number="SP-158/GKPB/OJK/X/2024",
    title="Siaran Pers: OJK Cabut Izin Usaha PT Investree Radhika Jaya",
    published_on=date(2024, 10, 21),
    language="id",
    url="https://ojk.go.id/id/berita-dan-kegiatan/siaran-pers/Pages/sp-158.aspx",
    citation="Siaran Pers OJK SP-158/GKPB/OJK/X/2024, 21 Oktober 2024",
    passages=3,
    published_at=PUBLISHED_AT,
)

REVOKED = Passage(REVOCATION_RELEASE, "p-1", 1, "Otoritas Jasa Keuangan (OJK) … mencabut izin usaha PT Investree…",
                  page_start=None, page_end=None)
