from datetime import date

import pytest
from market_samples import ALAMI, INVESTREE
from memory_market import DANA_SYARIAH, EDITION_2020, MemoryMarket

from metamorph_market_retrieval.application.companies import CompanyQuery, FindCompanies
from metamorph_retrieval_contract.errors import InvalidArgument
from metamorph_retrieval_contract.evidence import EmptyReason, Hit, Record
from metamorph_retrieval_contract.refs import Ref


def find(**query: object):  # noqa: ANN201 - a page of hits or of evidence
    return FindCompanies(MemoryMarket()).run(CompanyQuery(**query))  # type: ignore[arg-type]


def ids(page) -> list[str]:  # noqa: ANN001
    return [(item.evidence if isinstance(item, Hit) else item).ref.id for item in page.items]


def test_without_a_name_the_companies_filtered_come_by_legal_name() -> None:
    page = find(register="ojk:lpbbti", business_type="sharia", status="licensed")

    assert ids(page) == [ALAMI.id, DANA_SYARIAH.id]
    assert not isinstance(page.items[0], Hit)


def test_filters_that_exclude_every_company_say_so() -> None:
    page = find(business_type="sharia", status="left")

    assert (page.items, page.empty_reason) == ((), EmptyReason.FILTERS_EXCLUDE_ALL)


def test_a_name_ranks_the_companies_it_matches_as_hits() -> None:
    page = find(query="DANA SYARIAH")

    assert ids(page) == [DANA_SYARIAH.id]
    assert isinstance(hit := page.items[0], Hit) and (hit.rank, hit.score) == (1, 1.0)


def test_a_name_no_company_holds_is_no_match() -> None:
    assert find(query="Kapital Boost").empty_reason is EmptyReason.NO_MATCH


def test_on_a_past_date_the_edition_current_that_day_decides_who_was_listed_and_how() -> None:
    page = find(register="ojk:lpbbti", as_of=date(2020, 6, 30))

    assert ids(page) == [ALAMI.id, DANA_SYARIAH.id, INVESTREE.id]
    standing = {item.ref.id: (item.qualifiers.status, item.qualifiers.as_of) for item in page.items}
    assert standing[DANA_SYARIAH.id] == ("registered", EDITION_2020)
    assert standing[INVESTREE.id] == ("licensed", EDITION_2020)


def test_a_standing_on_a_past_date_filters_too() -> None:
    assert ids(find(as_of=date(2020, 6, 30), status="registered")) == [DANA_SYARIAH.id]


def test_before_the_first_edition_nobody_was_listed() -> None:
    assert find(as_of=date(2019, 1, 1)).empty_reason is EmptyReason.FILTERS_EXCLUDE_ALL


def test_announcements_name_the_release_passages_about_each_company() -> None:
    (company,) = find(query="Investree", announcements=True).items

    assert isinstance(body := company.evidence.body, Record)
    assert [item["ref"] for item in body.fields["announcements"]] == [
        "release:ojk:siaran-pers:2024:ojk-cabut-izin-usaha-pt-investree-radhika-jaya#p-1"
    ]
    assert "announcements" not in find(query="Investree").items[0].evidence.body.fields


def test_a_page_at_a_time_with_a_cursor_for_the_rest() -> None:
    first = find(register="ojk:lpbbti", limit=2)
    rest = find(register="ojk:lpbbti", limit=2, cursor=first.cursor)

    assert (ids(first), first.cursor) == ([ALAMI.id, DANA_SYARIAH.id], "2")
    assert (ids(rest), rest.cursor) == ([INVESTREE.id], None)


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ({"status": "active"}, "status 'active': licensed, registered or left"),
        ({"business_type": "islamic"}, "business_type 'islamic': sharia, conventional or unknown"),
        ({"status": "left", "as_of": date(2020, 6, 30)}, "status left: a company that left isn't on that day's"),
        ({"query": "  "}, "query: say which name"),
        ({"cursor": "page-two"}, "cursor 'page-two' is not one this tool gave"),
    ],
)
def test_arguments_that_cant_be_answered_are_refused_saying_what_would_be(query: dict, message: str) -> None:
    with pytest.raises(InvalidArgument, match=message):
        find(**query)


def test_a_company_evidence_names_its_ref() -> None:
    assert find(query="ALAMI").items[0].evidence.ref == Ref.parse("company:ojk:lpbbti:kep-21-d.05-2020")
