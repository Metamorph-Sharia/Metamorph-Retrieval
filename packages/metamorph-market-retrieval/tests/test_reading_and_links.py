import pytest
from memory_market import MemoryMarket

from metamorph_market_retrieval.application.links import NamedBy
from metamorph_market_retrieval.application.reading import MAX_WINDOW, Reading
from metamorph_retrieval_contract.errors import InvalidArgument, UnknownRef
from metamorph_retrieval_contract.evidence import EmptyReason, Figures, PageSpan, Record, Text
from metamorph_retrieval_contract.links import Direction, Link, LinkType
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest

R = Ref.parse
TARGETS = R("report:ojk:roadmap:2023:lpbbti#p-43")
REVOKED = R("release:ojk:siaran-pers:2024:ojk-cabut-izin-usaha-pt-investree-radhika-jaya#p-1")
INVESTREE = R("company:ojk:lpbbti:kep-45-d.05-2019")


def read(text: str, window: int = 0):  # noqa: ANN201
    return Reading(MemoryMarket()).read(R(text), window=window)


@pytest.mark.parametrize(
    ("ref", "kind"),
    [
        ("company:ojk:lpbbti:kep-21-d.05-2020", "company"),
        ("register:ojk:lpbbti", "register"),
        ("dataset:bi:seki:tabel1_1", "dataset"),
        ("series:bi:seki:tabel1_1:monthly:row=1", "series"),
        ("industry:ojk:portal:bank-umum-syariah", "industry"),
        ("sector:sharia-banking", "sector"),
        ("report:ojk:roadmap:2023:lpbbti", "report"),
        ("release:ojk:siaran-pers:2024:ojk-cabut-izin-usaha-pt-investree-radhika-jaya", "release"),
        ("report:ojk:roadmap:2023:lpbbti#p-43", "report"),
    ],
)
def test_every_market_ref_reads_as_its_evidence(ref: str, kind: str) -> None:
    evidence = read(ref)

    assert (str(evidence.ref), evidence.kind) == (ref, kind)


def test_a_series_reads_as_its_card_not_its_figures() -> None:
    assert isinstance(read("series:bi:seki:tabel1_1:monthly:row=1").body, Record)
    assert not isinstance(read("series:bi:seki:tabel1_1:monthly:row=1").body, Figures)


def test_a_passage_reads_with_its_neighbours_when_asked() -> None:
    evidence = read(str(TARGETS), window=1)

    assert isinstance(evidence.body, Text)
    assert evidence.body.pages == PageSpan(60, 63)
    assert evidence.body.wording.startswith("pengembangan ekosistem")


def test_a_window_is_bounded() -> None:
    with pytest.raises(InvalidArgument, match=f"window 9: 0 to {MAX_WINDOW}"):
        read(str(TARGETS), window=9)


@pytest.mark.parametrize("ref", ["report:ojk:lpksi:1999", "report:ojk:roadmap:2023:lpbbti#p-999",
                                 "company:ojk:lpbbti:none", "doc:ojk:pojk:2024:40", "sector:none",
                                 "industry:ojk:portal:none", "dataset:none", "register:none", "series:none:x"])
def test_a_ref_the_market_doesnt_hold_is_unknown(ref: str) -> None:
    with pytest.raises(UnknownRef, match=f"the market holds nothing under {ref}"):
        read(ref)


def test_describe_gives_cards_for_what_it_holds_in_the_order_asked() -> None:
    cards = Reading(MemoryMarket()).describe([R("sector:sharia-banking"), R("doc:ojk:pojk:2024:40"), TARGETS])

    assert [card.ref for card in cards] == [R("sector:sharia-banking"), TARGETS]
    assert all(card.body is None for card in cards)


def links(ref: Ref, **request: object):  # noqa: ANN201
    return NamedBy(MemoryMarket()).run(ref, LinksRequest(**request))  # type: ignore[arg-type]


def test_the_passages_naming_a_company_link_to_it() -> None:
    page = links(INVESTREE, direction=Direction.INCOMING)

    assert page.items == (Link(LinkType.NAMES, REVOKED, INVESTREE),)


def test_a_passage_links_to_what_it_names() -> None:
    page = links(REVOKED, direction=Direction.OUTGOING)

    assert [link.target for link in page.items] == [INVESTREE, R("doc:ojk:pojk:2022:10")]


def test_a_regulation_the_market_doesnt_own_is_linked_from_the_passages_naming_it() -> None:
    page = links(R("doc:ojk:pojk:2024:40"))

    assert page.items == (Link(LinkType.NAMES, R("report:ojk:roadmap:2023:lpbbti#p-44"), R("doc:ojk:pojk:2024:40")),)


def test_a_whole_document_links_to_everything_its_passages_name() -> None:
    whole = R("release:ojk:siaran-pers:2024:ojk-cabut-izin-usaha-pt-investree-radhika-jaya")

    assert len(links(whole, direction=Direction.OUTGOING).items) == 2


def test_the_market_knows_only_what_passages_name() -> None:
    assert links(INVESTREE, types=frozenset({LinkType.AMENDS})).empty_reason is EmptyReason.NO_MATCH


def test_a_company_no_passage_names_has_no_links() -> None:
    assert links(R("company:ojk:lpbbti:kep-21-d.05-2020")).empty_reason is EmptyReason.NO_MATCH
