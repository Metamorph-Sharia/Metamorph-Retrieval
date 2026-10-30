"""Records as the read model returns them, modelled on published (2026-10-30)."""

from datetime import UTC, date, datetime

from metamorph_regulation_standin.domain.records import Document, Unit

PUBLISHED_AT = datetime(2026, 10, 22, 14, 5, tzinfo=UTC)

POJK_40 = Document(
    id="ojk:pojk:2024:40",
    issuer="ojk",
    family="pojk",
    number="40",
    year=2024,
    citation="POJK 40 Tahun 2024",
    title="LAYANAN PENDANAAN BERSAMA BERBASIS TEKNOLOGI INFORMASI",
    kind="regulation",
    status="partly_revoked",
    status_as_of=date(2026, 10, 1),
    enacted_on=date(2024, 12, 20),
    promulgated_on=date(2024, 12, 27),
    effective_on=date(2024, 12, 27),
    aliases=("POJK 40/2024",),
    published_at=PUBLISHED_AT,
)

FATWA_117 = Document(
    id="dsnmui:fatwa:117",
    issuer="dsnmui",
    family="fatwa",
    number="117",
    year=2018,
    citation="Fatwa DSN-MUI No. 117/DSN-MUI/II/2018",
    title="LAYANAN PEMBIAYAAN BERBASIS TEKNOLOGI INFORMASI BERDASARKAN PRINSIP SYARIAH",
    kind="fatwa",
    status="unknown",
    status_as_of=None,
    enacted_on=date(2018, 2, 22),
    promulgated_on=None,
    effective_on=None,
    aliases=(),
    published_at=PUBLISHED_AT,
)

ARTICLE_5_1 = Unit(
    document=POJK_40,
    address="pasal-5/ayat-1",
    heading_path=("BAB II PENYELENGGARA", "Pasal 5", "(1)"),
    wording="Penyelenggara wajib berbentuk badan hukum perseroan terbatas atau koperasi.",
    page_start=6,
    page_end=6,
    valid_from=None,
    valid_to=None,
    under_review=False,
)

RULING = Unit(
    document=FATWA_117,
    address="diktum-kedua/angka-1",
    heading_path=("KEDUA", "1."),
    wording="Penyelenggaraan Layanan Pembiayaan Berbasis Teknologi Informasi wajib sesuai dengan prinsip syariah.",
    page_start=None,
    page_end=None,
    valid_from=None,
    valid_to=date(2030, 1, 1),
    under_review=True,
)
