"""The rule a provision's own status follows."""

from __future__ import annotations

from datetime import date

from metamorph_regulation_retrieval.domain import status
from metamorph_regulation_retrieval.domain.status import latest_events, provision_status

PARTLY_REVOKED_DOCUMENT = status.PARTLY_REVOKED


def test_a_provision_its_document_revoked_is_revoked():
    assert provision_status("pasal-5", status.REVOKED, {"pasal-5": status.IN_FORCE}) == status.REVOKED


def test_a_revoked_document_wins_over_any_address_event():
    events = {"pasal-5": status.AMENDED, "pasal-6/ayat-1": status.REVOKED}
    assert provision_status("pasal-5", status.REVOKED, events) == status.REVOKED


def test_a_not_yet_in_force_document_wins_over_any_address_event():
    events = {"pasal-5": status.REVOKED}
    assert provision_status("pasal-5", status.NOT_YET_IN_FORCE, events) == status.NOT_YET_IN_FORCE


def test_an_unknown_document_tells_nothing_more_about_its_provisions():
    events = {"pasal-5": status.AMENDED}
    assert provision_status("pasal-5", status.UNKNOWN, events) == status.UNKNOWN


def test_a_provision_with_its_own_event_reads_that_status():
    events = {"pasal-5": status.AMENDED}
    assert provision_status("pasal-5", PARTLY_REVOKED_DOCUMENT, events) == status.AMENDED


def test_an_article_whose_ayat_was_revoked_reads_partly_revoked():
    events = {"pasal-187/ayat-1": status.REVOKED}
    assert provision_status("pasal-187", PARTLY_REVOKED_DOCUMENT, events) == status.PARTLY_REVOKED


def test_an_article_whose_ayat_was_amended_reads_amended():
    events = {"pasal-187/ayat-1": status.AMENDED}
    assert provision_status("pasal-187", PARTLY_REVOKED_DOCUMENT, events) == status.AMENDED


def test_an_untouched_article_in_a_partly_revoked_document_with_events_reads_in_force():
    events = {"pasal-187/ayat-1": status.REVOKED}
    assert provision_status("pasal-5", PARTLY_REVOKED_DOCUMENT, events) == status.IN_FORCE


def test_the_same_document_without_events_reads_partly_revoked():
    assert provision_status("pasal-5", PARTLY_REVOKED_DOCUMENT, {}) == status.PARTLY_REVOKED


def test_an_ayat_of_a_revoked_article_reads_revoked_by_its_nearest_holder():
    events = {"pasal-187": status.REVOKED, "pasal-187/ayat-2": status.AMENDED}
    assert provision_status("pasal-187/ayat-2", PARTLY_REVOKED_DOCUMENT, events) == status.AMENDED
    assert provision_status("pasal-187/ayat-3", PARTLY_REVOKED_DOCUMENT, events) == status.REVOKED


def test_the_nearest_ancestor_wins_over_a_further_one():
    events = {"pasal-187": status.AMENDED, "pasal-187/ayat-1": status.REVOKED}
    assert provision_status("pasal-187/ayat-1/huruf-a", PARTLY_REVOKED_DOCUMENT, events) == status.REVOKED


def test_an_elucidation_follows_the_article_it_explains():
    events = {"pasal-187": status.REVOKED}
    address = "penjelasan/pasal-187"
    assert provision_status(address, PARTLY_REVOKED_DOCUMENT, events) == status.REVOKED


def test_an_elucidation_of_an_untouched_article_reads_in_force():
    events = {"pasal-187": status.REVOKED}
    address = "penjelasan/pasal-5"
    assert provision_status(address, PARTLY_REVOKED_DOCUMENT, events) == status.IN_FORCE


def test_an_elucidation_is_looked_up_as_the_article_it_explains():
    # The elucidation reads as `pasal-5`, which its own event leaves untouched.
    events = {"penjelasan/pasal-5": status.AMENDED}
    assert provision_status("penjelasan/pasal-5", PARTLY_REVOKED_DOCUMENT, events) == status.IN_FORCE


def test_the_bare_elucidation_section_follows_no_article():
    events = {"pasal-187": status.REVOKED}
    assert provision_status("penjelasan", PARTLY_REVOKED_DOCUMENT, events) == status.IN_FORCE
    assert provision_status("penjelasan", PARTLY_REVOKED_DOCUMENT, {}) == PARTLY_REVOKED_DOCUMENT


def test_a_whole_document_event_is_read_as_an_event_of_that_address():
    events = {"pasal-5": status.AMENDED}
    assert provision_status("pasal-5", status.IN_FORCE, events) == status.AMENDED


def test_latest_events_keeps_the_latest_dated_event_per_address():
    rows = [
        ("pasal-5", status.AMENDED, date(2023, 1, 1)),
        ("pasal-5", status.REVOKED, date(2024, 6, 1)),
        ("pasal-6", status.REVOKED, date(2024, 1, 1)),
    ]
    assert latest_events(rows) == {"pasal-5": status.REVOKED, "pasal-6": status.REVOKED}


def test_latest_events_counts_an_undated_event_as_earlier_than_any_dated_one():
    rows = [
        ("pasal-5", status.REVOKED, None),
        ("pasal-5", status.AMENDED, date(2023, 1, 1)),
    ]
    assert latest_events(rows) == {"pasal-5": status.AMENDED}
    rows = [
        ("pasal-5", status.AMENDED, date(2023, 1, 1)),
        ("pasal-5", status.REVOKED, None),
    ]
    assert latest_events(rows) == {"pasal-5": status.AMENDED}


def test_latest_events_lets_the_later_row_win_on_equal_dates():
    rows = [
        ("pasal-5", status.AMENDED, date(2023, 1, 1)),
        ("pasal-5", status.REVOKED, date(2023, 1, 1)),
    ]
    assert latest_events(rows) == {"pasal-5": status.REVOKED}


def test_latest_events_with_no_rows_is_empty():
    assert latest_events([]) == {}


def test_the_build_reads_each_documents_events_as_their_latest_status_per_address() -> None:
    from datetime import date

    from metamorph_regulation_retrieval.indexing.build import events_by_document

    rows = [
        ("ojk:pojk:2024:40", "pasal-187", "amended", date(2025, 1, 1)),
        ("ojk:pojk:2024:40", "pasal-187", "revoked", date(2026, 7, 6)),
        ("ojk:pojk:2023:22", "pasal-5", "amended", None),
    ]

    assert events_by_document(rows) == {"ojk:pojk:2024:40": {"pasal-187": "revoked"},
                                        "ojk:pojk:2023:22": {"pasal-5": "amended"}}
