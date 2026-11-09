"""The outline rule, and the record fields a document's card gets from it."""

from metamorph_regulation_retrieval.domain.evidence import document_evidence
from metamorph_regulation_retrieval.domain.outline import OutlineProvision, document_outline
from metamorph_regulation_retrieval.indexing.build import outlines

DOC = "ojk:pojk:2024:40"


def unit(address: str, *, kind: str = "pasal", parent: str | None = None, ordinal: int = 0, depth: int = 0,
         path: tuple[str, ...] = ()) -> OutlineProvision:
    return OutlineProvision(address, kind, parent, ordinal, depth, path)


def card(output: list[dict]) -> dict:
    return document_evidence({"document_id": DOC, "outline": output}, provider="regulation", index_version="v")


def test_articles_are_grouped_under_their_chapter_and_part() -> None:
    rows = [
        unit("menimbang", kind="menimbang", ordinal=0, path=("Menimbang",)),
        unit("mengingat", kind="mengingat", ordinal=1, path=("Mengingat",)),
        unit("bab-i", kind="bab", ordinal=2, path=("BAB I KETENTUAN UMUM",)),
        unit("pasal-1", parent="bab-i", ordinal=3, depth=1, path=("BAB I KETENTUAN UMUM", "Pasal 1")),
        unit("bab-ii", kind="bab", ordinal=4, path=("BAB II BENTUK BADAN HUKUM",)),
        unit("bagian-kesatu", kind="bagian", parent="bab-ii", ordinal=5, depth=1,
             path=("BAB II BENTUK BADAN HUKUM", "Bagian Kesatu Bentuk Badan Hukum")),
        unit("pasal-2", parent="bagian-kesatu", ordinal=6, depth=2,
             path=("BAB II BENTUK BADAN HUKUM", "Bagian Kesatu Bentuk Badan Hukum", "Pasal 2")),
        unit("pasal-3", parent="bagian-kesatu", ordinal=7, depth=2,
             path=("BAB II BENTUK BADAN HUKUM", "Bagian Kesatu Bentuk Badan Hukum", "Pasal 3")),
        unit("penjelasan", kind="penjelasan", ordinal=8, path=("PENJELASAN",)),
    ]

    assert document_outline(rows) == [
        {"heading": None, "units": ["menimbang", "mengingat"]},
        {"heading": "BAB I KETENTUAN UMUM", "units": ["pasal-1"]},
        {"heading": "BAB II BENTUK BADAN HUKUM > Bagian Kesatu Bentuk Badan Hukum", "units": ["pasal-2", "pasal-3"]},
        {"heading": None, "units": ["penjelasan"]},
    ]


def test_an_ayat_or_huruf_inside_an_article_is_not_a_unit() -> None:
    rows = [
        unit("bab-i", kind="bab", ordinal=0, path=("BAB I",)),
        unit("pasal-1", parent="bab-i", ordinal=1, depth=1, path=("BAB I", "Pasal 1")),
        unit("pasal-1/ayat-1", kind="ayat", parent="pasal-1", ordinal=2, depth=2, path=("BAB I", "Pasal 1", "(1)")),
        unit("pasal-1/ayat-1/huruf-a", kind="huruf", parent="pasal-1/ayat-1", ordinal=3, depth=3,
             path=("BAB I", "Pasal 1", "(1)", "a.")),
    ]

    assert document_outline(rows) == [{"heading": "BAB I", "units": ["pasal-1"]}]


def test_a_fatwa_like_document_has_one_group_without_headings() -> None:
    rows = [
        unit("menimbang", kind="menimbang", ordinal=0, path=("Menimbang",)),
        unit("mengingat", kind="mengingat", ordinal=1, path=("Mengingat",)),
        unit("memutuskan", kind="memutuskan", ordinal=2, path=("MEMUTUSKAN",)),
        unit("diktum-pertama", kind="diktum", ordinal=3, path=("Pertama : Ketentuan Umum",)),
        unit("diktum-pertama/angka-1", kind="angka", parent="diktum-pertama", ordinal=4, depth=1,
             path=("Pertama : Ketentuan Umum", "1.")),
        unit("diktum-kedua", kind="diktum", ordinal=5, path=("Kedua : Ketentuan Khusus",)),
    ]

    assert document_outline(rows) == [
        {"heading": None, "units": ["menimbang", "mengingat", "memutuskan", "diktum-pertama", "diktum-kedua"]}
    ]


def test_units_come_by_ordinal_not_by_the_order_read() -> None:
    rows = [
        unit("pasal-2", ordinal=2, path=("Pasal 2",)),
        unit("pasal-1", ordinal=1, path=("Pasal 1",)),
        unit("pasal-3", ordinal=3, path=("Pasal 3",)),
    ]

    assert document_outline(rows) == [{"heading": None, "units": ["pasal-1", "pasal-2", "pasal-3"]}]


def test_a_documents_card_carries_its_outline_and_how_to_read_a_unit() -> None:
    outline = [{"heading": "BAB III PERIZINAN USAHA", "units": ["pasal-10", "pasal-11"]}]

    fields = card(outline)["body"]["fields"]

    assert fields["outline"] == outline
    assert fields["outline_reading"] == (
        "Read a unit as this document's ref with #address, e.g. doc:ojk:pojk:2024:40#pasal-10."
    )


def test_a_documents_card_without_an_outline_has_neither_field() -> None:
    fields = card([])["body"]["fields"]

    assert "outline" not in fields
    assert "outline_reading" not in fields


def test_the_build_outlines_each_document_from_its_provision_rows() -> None:
    rows = [
        ("ojk:pojk:2024:40", "bab-i", "bab", None, 1, 0, ["BAB I"], "KETENTUAN UMUM"),
        ("ojk:pojk:2024:40", "pasal-1", "pasal", "bab-i", 2, 1, ["BAB I", "Pasal 1"], None),
        ("dsnmui:fatwa:117", "diktum-pertama", "diktum", None, 1, None, None, ": Ketentuan Umum"),
    ]

    assert outlines(rows) == {
        "ojk:pojk:2024:40": [{"heading": "BAB I", "units": ["pasal-1"]}],
        "dsnmui:fatwa:117": [{"heading": None, "units": ["diktum-pertama"],
                              "titles": {"diktum-pertama": "Ketentuan Umum"}}],
    }
