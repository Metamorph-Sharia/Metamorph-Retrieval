"""The outline rule, and the record fields a document's card gets from it."""

from metamorph_regulation_retrieval.domain.evidence import document_evidence
from metamorph_regulation_retrieval.domain.outline import OutlineProvision, document_outline
from metamorph_regulation_retrieval.indexing.build import outlines

DOC = "ojk:pojk:2024:40"


def unit(address: str, *, kind: str = "pasal", parent: str | None = None, ordinal: int = 0, depth: int = 0,
         path: tuple[str, ...] = (), length: int = 0) -> OutlineProvision:
    return OutlineProvision(address, kind, parent, ordinal, depth, path, length=length)


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


def test_a_regulation_without_chapters_has_its_articles_under_the_decision() -> None:
    rows = [
        unit("menimbang", kind="menimbang", ordinal=0, path=("Menimbang",)),
        unit("mengingat", kind="mengingat", ordinal=1, path=("Mengingat",)),
        unit("memutuskan", kind="memutuskan", ordinal=2, path=("MEMUTUSKAN",)),
        unit("pasal-1", parent="memutuskan", ordinal=3, depth=1, path=("MEMUTUSKAN", "Pasal 1")),
        unit("pasal-1/ayat-1", kind="ayat", parent="pasal-1", ordinal=4, depth=2,
             path=("MEMUTUSKAN", "Pasal 1", "(1)")),
        unit("pasal-2", parent="memutuskan", ordinal=5, depth=1, path=("MEMUTUSKAN", "Pasal 2")),
        unit("pengesahan", kind="pengesahan", ordinal=6, path=("Pengesahan",)),
    ]

    assert document_outline(rows) == [
        {"heading": None, "units": ["menimbang", "mengingat"]},
        {"heading": "MEMUTUSKAN", "units": ["pasal-1", "pasal-2"]},
        {"heading": None, "units": ["pengesahan"]},
    ]


def test_an_amendment_reads_as_its_pasal_i_and_pasal_ii_with_what_pasal_i_quotes_inside() -> None:
    rows = [
        unit("menimbang", kind="menimbang", ordinal=0, path=("Menimbang",)),
        unit("memutuskan", kind="memutuskan", ordinal=1, path=("MEMUTUSKAN",)),
        unit("pasal-i", parent="memutuskan", ordinal=2, depth=1, path=("MEMUTUSKAN", "Pasal I")),
        unit("pasal-i/pasal-13", parent="pasal-i", ordinal=3, depth=2, path=("MEMUTUSKAN", "Pasal I", "Pasal 13")),
        unit("pasal-i/pasal-13/ayat-2", kind="ayat", parent="pasal-i/pasal-13", ordinal=4, depth=3,
             path=("MEMUTUSKAN", "Pasal I", "Pasal 13", "(2)")),
        unit("pasal-ii", parent="memutuskan", ordinal=5, depth=1, path=("MEMUTUSKAN", "Pasal II")),
        unit("penjelasan", kind="penjelasan", ordinal=6, path=("PENJELASAN",)),
    ]

    assert document_outline(rows) == [
        {"heading": None, "units": ["menimbang"]},
        {"heading": "MEMUTUSKAN", "units": ["pasal-i", "pasal-ii"]},
        {"heading": None, "units": ["penjelasan"]},
    ]


def test_an_amendment_too_long_to_read_at_once_reads_as_the_articles_it_changes() -> None:
    rows = [
        unit("memutuskan", kind="memutuskan", ordinal=0, path=("MEMUTUSKAN",), length=200_000),
        unit("pasal-i", parent="memutuskan", ordinal=1, depth=1, path=("MEMUTUSKAN", "Pasal I"), length=196_000),
        unit("pasal-i/pasal-4", parent="pasal-i", ordinal=2, depth=2, path=("MEMUTUSKAN", "Pasal I", "Pasal 4"),
             length=3_000),
        unit("pasal-i/pasal-4/ayat-1", kind="ayat", parent="pasal-i/pasal-4", ordinal=3, depth=3, length=900),
        unit("pasal-i/pasal-13", parent="pasal-i", ordinal=4, depth=2, path=("MEMUTUSKAN", "Pasal I", "Pasal 13"),
             length=2_000),
        unit("pasal-ii", parent="memutuskan", ordinal=5, depth=1, path=("MEMUTUSKAN", "Pasal II"), length=5_000),
    ]

    assert document_outline(rows) == [
        {"heading": "MEMUTUSKAN > Pasal I", "units": ["pasal-i/pasal-4", "pasal-i/pasal-13"]},
        {"heading": "MEMUTUSKAN", "units": ["pasal-ii"]},
    ]


def test_nothing_inside_a_unit_is_looked_at_even_when_its_structure_is_odd() -> None:
    rows = [
        unit("memutuskan", kind="memutuskan", ordinal=0, path=("MEMUTUSKAN",)),
        unit("pasal-i", parent="memutuskan", ordinal=1, depth=1, path=("MEMUTUSKAN", "Pasal I"), length=8_000),
        unit("pasal-i/pasal-52a", parent="pasal-i", ordinal=2, depth=2, path=("MEMUTUSKAN", "Pasal I", "Pasal 52A")),
        # the parser filed another article's ayat under Pasal 52A: inside a unit, so the outline doesn't see it
        unit("pasal-i/pasal-4/ayat-1", kind="ayat", parent="pasal-i/pasal-52a", ordinal=3, depth=3),
    ]

    assert document_outline(rows) == [{"heading": "MEMUTUSKAN", "units": ["pasal-i"]}]


def test_what_the_index_cant_read_is_a_heading_over_what_it_can_or_left_out() -> None:
    rows = [
        unit("pasal-1", ordinal=0, path=("Pasal 1",)),
        unit("pengesahan", kind="pengesahan", ordinal=1, path=("Pengesahan",)),
        unit("penjelasan", kind="penjelasan", ordinal=2, path=("PENJELASAN",)),
        unit("penjelasan/umum", kind="umum", parent="penjelasan", ordinal=3, depth=1, path=("PENJELASAN", "Umum")),
        unit("penjelasan/pasal-1", parent="penjelasan", ordinal=4, depth=1, path=("PENJELASAN", "Pasal 1")),
    ]

    assert document_outline(rows, readable={"pasal-1", "penjelasan/umum", "penjelasan/pasal-1"}) == [
        {"heading": None, "units": ["pasal-1"]},
        {"heading": "PENJELASAN", "units": ["penjelasan/umum", "penjelasan/pasal-1"]},
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
