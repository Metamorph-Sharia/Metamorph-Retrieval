from metamorph_regulation_retrieval.indexing.chunks import (
    Provision,
    chunk,
    clean,
    provision_label,
    significance_flags,
)


def provision(
    body: str = "Batas maksimum adalah Rp 4.000.000.000,00.",
    *,
    title: str = "LAYANAN PENDANAAN BERSAMA",
    heading_path: tuple[str, ...] = (),
) -> Provision:
    return Provision(
        document_id="ojk:pojk:2024:40",
        text_sha256="abc",
        address="pasal-137/ayat-3",
        kind="ayat",
        label="Pasal 137 ayat (3)",
        heading=None,
        issuer="ojk",
        status="partly_revoked",
        valid_from=None,
        valid_to=None,
        body=body,
        title=title,
        citation="POJK 40/2024",
        heading_path=heading_path,
    )


def test_cleaning_removes_page_markers_and_urls() -> None:
    text, had_markers = clean("Halo <!-- page 3 --> dunia https://example.test/x  selesai")

    assert had_markers is True
    assert "page" not in text
    assert "https://" not in text
    assert "  " not in text


def test_a_sufficiently_clear_article_is_flagged_and_not_searchable() -> None:
    flags = significance_flags("Cukup jelas.", None)
    chunked = chunk(provision("Cukup jelas."), "test")

    assert "cukup_jelas" in flags
    assert chunked.searchable is False


def test_a_provision_that_only_marks_its_parts_clear_says_nothing() -> None:
    assert "cukup_jelas" in significance_flags("Ayat (1)\nCukup jelas.\nAyat (2)\nCukup jelas.", None)
    assert "dihapus" in significance_flags("Pasal 95 Dihapus.", None)


def test_a_running_header_is_not_wording() -> None:
    body = "Pasal 7 Cukup jelas. TAMBAHAN LEMBARAN NEGARA REPUBLIK INDONESIA NOMOR 6437"

    assert "cukup_jelas" in significance_flags(body, None)


def test_a_provision_that_mentions_the_words_keeps_its_wording() -> None:
    deleted = "Berdasarkan perubahan sanksi sebagaimana dimaksud pada ayat (4), sanksi denda dinyatakan dihapus."
    mixed = 'Huruf a Cukup jelas. Huruf b Yang dimaksud dengan "penerima dana" adalah pihak yang menerima pendanaan.'

    assert significance_flags(deleted, None) == []
    assert significance_flags(mixed, None) == []


def test_a_real_article_stays_searchable() -> None:
    chunked = chunk(provision(), "test")

    assert chunked.searchable is True
    assert chunked.flags == []


def test_a_provision_that_is_not_a_retrieval_unit_is_kept_for_reading_but_not_searched() -> None:
    from dataclasses import replace

    article = chunk(replace(provision(), address="pasal-137", kind="pasal", unit=False), "test")

    assert article.searchable is False and "not_a_unit" in article.flags


def test_the_context_carries_the_title_and_the_written_address() -> None:
    chunked = chunk(provision(), "test")

    assert chunked.context_text.startswith("POJK 40/2024\nLAYANAN PENDANAAN BERSAMA\nPasal 137, ayat (3)\n")
    assert chunked.token_count == len(chunked.context_text.split())


def test_the_context_carries_the_headings_above_the_provision() -> None:
    path = ("BAB XII KEGIATAN USAHA", "Bagian Kedua Batas Maksimum Pendanaan", "Pasal 137", "(3)")

    context = chunk(provision(heading_path=path), "test").context_text

    assert context.splitlines()[2] == "BAB XII KEGIATAN USAHA > Bagian Kedua Batas Maksimum Pendanaan"


def test_a_heading_that_only_marks_a_place_is_left_out() -> None:
    path = ("BAB II", "Pasal 137", "Ayat (3)", "(3)", "a.", "1.")

    context = chunk(provision(heading_path=path), "test").context_text

    assert context.splitlines()[2] == "Pasal 137, ayat (3)"


def test_the_chunk_id_is_stable_for_the_same_text() -> None:
    assert chunk(provision(), "test").chunk_id == chunk(provision(), "test").chunk_id
    assert chunk(provision(), "test").chunk_id != chunk(provision("Lain."), "test").chunk_id


def test_the_chunk_id_changes_with_what_the_model_reads() -> None:
    """A vector belongs to the text embedded: a build seeded with another's must not keep one its context outgrew."""
    plain, headed = chunk(provision(), "test"), chunk(provision(heading_path=("BAB I KETENTUAN UMUM",)), "test")

    assert plain.body == headed.body
    assert plain.chunk_id != headed.chunk_id
    assert chunk(provision(title="LAIN"), "test").chunk_id != plain.chunk_id


def test_addresses_are_written_as_a_lawyer_writes_them() -> None:
    assert provision_label("pasal-137/ayat-3/huruf-b") == "Pasal 137, ayat (3), huruf b"
