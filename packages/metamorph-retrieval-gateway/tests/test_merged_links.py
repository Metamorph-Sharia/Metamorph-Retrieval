"""Links several providers know go to each of them, and come back merged: both layers' on the first page, the owner's
first, with a cursor of the gateway's own."""

from collections.abc import Sequence
from dataclasses import replace

import pytest
from fakes import POJK_40, Regulations
from memory_provider import MemoryProvider

from metamorph_retrieval_contract.errors import InvalidArgument, ProviderUnavailable
from metamorph_retrieval_contract.evidence import EmptyReason, Page
from metamorph_retrieval_contract.links import Link, LinkType
from metamorph_retrieval_contract.provider import Manifest
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import MAX_LIMIT, LinksRequest
from metamorph_retrieval_gateway.application.gateway import Gateway

REVOKES = Link(LinkType.REVOKES, Ref.parse("doc:ojk:pojk:2025:1"), POJK_40)
AMENDS = Link(LinkType.AMENDS, Ref.parse("doc:ojk:pojk:2025:2"), POJK_40)
REFERS = Link(LinkType.REFERS_TO, Ref.parse("doc:ojk:pojk:2025:3"), POJK_40)
NAMED = Link(LinkType.NAMES, Ref.parse("release:ojk:sp:2025:1#p-1"), POJK_40)
NAMED_AGAIN = Link(LinkType.NAMES, Ref.parse("report:ojk:lpksi:2025#p-1"), POJK_40)


class Linking(Regulations):
    """Regulations with these links, paged by offset; or failing."""

    def __init__(self, links: Sequence[Link] = (), *, fails: Exception | None = None) -> None:
        super().__init__()
        self.all_links, self.fails = tuple(links), fails

    def manifest(self) -> Manifest:
        return replace(super().manifest(), links=True)

    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        if self.fails:
            raise self.fails
        start = int(request.cursor or 0)
        found = self.all_links[start:start + request.limit]
        if not found:
            return Page.empty(EmptyReason.NO_MATCH)
        following = start + request.limit
        return Page(found, cursor=str(following) if following < len(self.all_links) else None)


def market(*links: Link, fails: Exception | None = None) -> MemoryProvider | Linking:
    """The market's side: a provider joined under another name, owning no doc: refs."""

    class Market(Linking):
        def manifest(self) -> Manifest:
            return replace(super().manifest(), name="market", namespaces=frozenset({"release", "report"}))

    return Market(links, fails=fails)


def test_links_come_from_every_provider_that_answers_them() -> None:
    page = Gateway([market(NAMED), Linking([REVOKES])]).links(POJK_40, LinksRequest())

    assert set(page.items) == {NAMED, REVOKES}


def test_the_owner_of_the_ref_answers_first_and_the_others_take_turns() -> None:
    page = Gateway([market(NAMED, NAMED_AGAIN), Linking([REVOKES, AMENDS, REFERS])]).links(POJK_40, LinksRequest())

    assert page.items == (REVOKES, NAMED, AMENDS, NAMED_AGAIN, REFERS)


def test_a_passage_goes_first_to_the_layer_that_owns_it() -> None:
    passage = Ref.parse("release:ojk:sp:2025:1#p-1")
    page = Gateway([market(NAMED), Linking([REVOKES])]).links(passage, LinksRequest())

    assert page.items == (NAMED, REVOKES)


def test_a_link_both_providers_know_appears_once() -> None:
    page = Gateway([market(NAMED), Linking([NAMED])]).links(POJK_40, LinksRequest())

    assert page.items == (NAMED,)


def test_the_merged_links_page_with_the_gateways_own_cursor() -> None:
    gateway = Gateway([market(NAMED, NAMED_AGAIN), Linking([REVOKES, AMENDS, REFERS])])

    first = gateway.links(POJK_40, LinksRequest(limit=2))
    second = gateway.links(POJK_40, LinksRequest(limit=2, cursor=first.cursor))
    third = gateway.links(POJK_40, LinksRequest(limit=2, cursor=second.cursor))

    assert [*first.items, *second.items, *third.items] == [REVOKES, NAMED, AMENDS, NAMED_AGAIN, REFERS]
    assert first.cursor == "fused:2" and third.cursor is None


def test_links_page_past_what_one_provider_call_may_return() -> None:
    many = [Link(LinkType.REFERS_TO, Ref.parse(f"doc:ojk:pojk:2025:{number}"), POJK_40)
            for number in range(MAX_LIMIT * 2 + 3)]
    gateway = Gateway([market(NAMED), Linking(many)])

    seen, cursor = [], None
    while True:
        page = gateway.links(POJK_40, LinksRequest(limit=MAX_LIMIT, cursor=cursor))
        seen += page.items
        cursor = page.cursor
        if cursor is None:
            break

    assert len(seen) == len(set(seen)) == len(many) + 1


def test_a_provider_that_fails_leaves_the_others_links_and_a_warning() -> None:
    gateway = Gateway([market(fails=ProviderUnavailable("market is down")), Linking([REVOKES])])

    page = gateway.links(POJK_40, LinksRequest())

    assert page.items == (REVOKES,)
    assert page.warnings == ("market: market is down",)


def test_when_nothing_is_found_and_a_provider_failed_the_call_fails() -> None:
    gateway = Gateway([market(fails=ProviderUnavailable("market is down")), Linking()])

    with pytest.raises(ProviderUnavailable):
        gateway.links(POJK_40, LinksRequest())


def test_no_links_anywhere_is_an_empty_page() -> None:
    page = Gateway([market(), Linking()]).links(POJK_40, LinksRequest())

    assert page.items == () and page.empty_reason is EmptyReason.NO_MATCH


def test_a_cursor_the_gateway_did_not_give_is_invalid() -> None:
    with pytest.raises(InvalidArgument, match="cursor"):
        Gateway([market(NAMED), Linking([REVOKES])]).links(POJK_40, LinksRequest(cursor="12"))
