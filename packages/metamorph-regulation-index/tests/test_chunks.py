from metamorph_regulation_index.chunks import (
    Provision,
    chunk,
    clean,
    provision_label,
    significance_flags,
)


def provision(body: str = "Batas maksimum adalah Rp 4.000.000.000,00.") -> Provision:
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
        title="LAYANAN PENDANAAN BERSAMA",
        citation="POJK 40/2024",
    )


def test_cleaning_removes_page_markers_and_urls() -> None:
    text, had_markers = clean("Halo <!-- page 3 --> dunia https://example.test/x  selesai")

    assert had_markers is True
    assert "page" not in text
    assert "https://" not in text
    assert "  " not in text


def test_a_sufficiently_clear_article_is_flagged_and_not_searchable() -> None:
    flags = significance_flags("Cukup jelas.", None, None)
    chunked = chunk(provision("Cukup jelas."), "test")

    assert "cukup_jelas" in flags
    assert chunked.searchable is False


def test_a_real_article_stays_searchable() -> None:
    chunked = chunk(provision(), "test")

    assert chunked.searchable is True
    assert chunked.flags == []


def test_the_context_carries_the_title_and_the_written_address() -> None:
    chunked = chunk(provision(), "test")

    assert chunked.context_text.startswith("LAYANAN PENDANAAN BERSAMA\nPasal 137, ayat (3)\n")
    assert chunked.token_count == len(chunked.context_text.split())


def test_the_chunk_id_is_stable_for_the_same_text() -> None:
    assert chunk(provision(), "test").chunk_id == chunk(provision(), "test").chunk_id
    assert chunk(provision(), "test").chunk_id != chunk(provision("Lain."), "test").chunk_id


def test_addresses_are_written_as_a_lawyer_writes_them() -> None:
    assert provision_label("pasal-137/ayat-3/huruf-b") == "Pasal 137, ayat (3), huruf b"
