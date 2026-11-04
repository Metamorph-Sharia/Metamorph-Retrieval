from datetime import UTC, date, datetime

import pytest

from metamorph_regulation_retrieval.adapters.provider import FIND, NO_LINKS, NO_WORDS, NOT_DATED, RegulationProvider
from metamorph_regulation_retrieval.domain.filters import NO_FILTERS, Filters
from metamorph_regulation_retrieval.domain.links import ORDER, LinkRow
from metamorph_regulation_retrieval.domain.passage import Passage
from metamorph_retrieval_contract.conformance import Samples, ToolCall, conformance_problems
from metamorph_retrieval_contract.errors import UnknownRef, UnknownTool
from metamorph_retrieval_contract.evidence import EmptyReason, LegalForce
from metamorph_retrieval_contract.links import Direction, Link, LinkType
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest, Sort

PUBLISHED = datetime(2026, 10, 30, 8, 3, tzinfo=UTC)
DOC = "ojk:pojk:2024:40"

PASSAGES = [
    Passage(
        chunk_id="c1", document_id=DOC, address="pasal-137/ayat-3",
        title="LAYANAN PENDANAAN BERSAMA", citation="POJK 40/2024, Pasal 137 ayat (3)",
        text="Batas maksimum pemberian pendanaan adalah Rp 4.000.000.000.",
        doc_kind="regulation", doc_status="partly_revoked", valid_from=None, valid_to=None,
        effective_on=None, promulgated_on=None, published_at=PUBLISHED, issuer="ojk",
        family="pojk", number="40", year=2024, doc_citation="POJK 10/POJK.05/2022",
    ),
    Passage(
        chunk_id="c2", document_id=DOC, address="pasal-137/ayat-4",
        title="LAYANAN PENDANAAN BERSAMA", citation="POJK 40/2024, Pasal 137 ayat (4)",
        text="Batas maksimum ditetapkan berdasarkan kualitas pendanaan.",
        doc_kind="regulation", doc_status="partly_revoked", valid_from=None, valid_to=None,
        effective_on=None, promulgated_on=None, published_at=PUBLISHED, issuer="ojk",
        family="pojk", number="40", year=2024, doc_citation="POJK 10/POJK.05/2022",
    ),
]


LINK_ROWS = [
    LinkRow("revokes", "ojk:pojk:2025:1", None, DOC, None, date(2025, 1, 1), "high"),
    LinkRow("amends", "ojk:pojk:2025:2", "pasal-i", DOC, "pasal-137/ayat-3", date(2025, 6, 1), "medium"),
    LinkRow("legal_basis", DOC, None, "id:uu:2011:21", None, date(2024, 12, 20), "high"),
]


class FakeStore:
    """Finds every passage by meaning, in order; by words, those holding a word of the question."""

    def __init__(self, *, dated: bool = True, words: bool = True, linked: bool = True) -> None:
        self.asked: list[Filters] = []
        self.dated = dated
        self.words = words
        self.linked = linked

    def by_meaning(self, vector, limit, filters=NO_FILTERS):
        self.asked.append(filters)
        return [(passage, 0.8 - index / 100) for index, passage in enumerate(self._kept(filters)[:limit])]

    def by_words(self, query, limit, filters=NO_FILTERS):
        asked = set(query.lower().split())
        held = [passage for passage in self._kept(filters) if asked & set(passage.text.lower().rstrip(".").split())]
        return [(passage, 1.0) for passage in held[:limit]]

    def matches_words(self):
        return self.words

    def dates_revocations(self):
        return self.dated

    def holds_links(self):
        return self.linked

    def links(self, document_id, address, *, incoming, outgoing, types, limit, offset):
        self.asked_links = (document_id, address, incoming, outgoing, types)
        return LINK_ROWS[offset:offset + limit]

    @staticmethod
    def _kept(filters):
        return [passage for passage in PASSAGES if not filters.kinds or passage.doc_kind in filters.kinds]

    def read(self, document_id, address):
        return next(
            (p for p in PASSAGES if p.document_id == document_id and p.address == address), None
        )

    def document(self, document_id):
        if document_id != DOC:
            return None
        return {
            "document_id": DOC, "kind": "regulation", "citation": "POJK 10/POJK.05/2022",
            "title": "LAYANAN PENDANAAN BERSAMA", "issuer": "ojk", "status": "partly_revoked",
            "family": "pojk", "number": "40", "year": 2024, "promulgated_on": None,
            "effective_on": None, "published_at": PUBLISHED, "aliases": ["POJK 40/2024"],
        }

    def published_at(self):
        return PUBLISHED


class FakeEmbedder:
    def encode(self, text):
        return [0.0] * 1024


def provider(store: FakeStore | None = None) -> RegulationProvider:
    return RegulationProvider(store or FakeStore(), FakeEmbedder())


SAMPLES = Samples(
    refs=(Ref.parse(f"doc:{DOC}#pasal-137/ayat-3"), Ref.parse(f"doc:{DOC}#pasal-137/ayat-4")),
    unknown=Ref.parse("doc:ojk:pojk:2099:1"),
    query="batas maksimum pemberian pendanaan",
    tool_calls=(ToolCall(FIND, {"citation": "POJK 40/2024 Pasal 137 ayat (3)"}),),
    linked=Ref.parse(f"doc:{DOC}"),
)


def test_the_regulatory_provider_keeps_the_retrieval_contract() -> None:
    assert conformance_problems(provider(), SAMPLES) == []


def test_it_owns_doc_refs_and_offers_exact_lookup() -> None:
    manifest = provider().manifest()

    assert manifest.namespaces == frozenset({"doc"})
    assert "fatwa" in manifest.kinds
    assert manifest.links is True
    assert [tool.name for tool in manifest.tools] == [FIND]


def test_search_returns_ranked_evidence() -> None:
    page = provider().search(SearchRequest("batas pendanaan", limit=2))

    assert [item.rank for item in page.items] == [1, 2]
    assert page.items[0].evidence.ref == Ref.parse(f"doc:{DOC}#pasal-137/ayat-3")
    assert page.items[0].evidence.legal_force.value == "binding"


def test_search_warns_about_filters_it_cannot_apply() -> None:
    page = provider().search(SearchRequest("batas", published_from=date(2024, 1, 1), sort=Sort.NEWEST))

    assert any(warning.startswith("published_from") for warning in page.warnings)
    assert any(warning.startswith("sort") for warning in page.warnings)


def test_the_filters_reach_the_store() -> None:
    store = FakeStore()
    page = provider(store).search(SearchRequest(
        "batas", issuers=frozenset({"ojk"}), documents=(Ref.parse(f"doc:{DOC}"),), in_force_on=date(2025, 3, 1)))

    assert store.asked == [Filters(issuers=frozenset({"ojk"}), documents=(DOC,),
                                   in_force_on=date(2025, 3, 1))]
    assert page.warnings == ()


def test_legal_force_narrows_the_kinds() -> None:
    store = FakeStore()
    provider(store).search(SearchRequest("batas", legal_force=frozenset({LegalForce.SHARIA})))

    assert store.asked[0].kinds == frozenset({"fatwa", "guideline", "circular"})


def test_legal_force_no_regulation_has_is_an_empty_page_without_a_search() -> None:
    store = FakeStore()
    page = provider(store).search(SearchRequest("batas", legal_force=frozenset({LegalForce.NONE})))

    assert page.empty_reason.value == "filters_exclude_all" and store.asked == []


def test_a_search_without_filters_that_finds_nothing_is_no_match() -> None:
    page = provider(FakeStore()).search(SearchRequest("batas", cursor="5"))

    assert page.items == () and page.empty_reason.value == "no_match"


def test_an_index_without_revocation_dates_says_what_in_force_on_kept() -> None:
    page = provider(FakeStore(dated=False)).search(SearchRequest("batas", in_force_on=date(2024, 6, 1)))

    assert page.warnings == (NOT_DATED,)


def test_a_unit_found_by_words_and_by_meaning_ranks_first_and_says_so() -> None:
    page = provider().search(SearchRequest("kualitas"))  # only ayat (4) holds the word

    assert page.items[0].evidence.ref == Ref.parse(f"doc:{DOC}#pasal-137/ayat-4")
    assert {matched.value for matched in page.items[0].matched_by} == {"words", "semantic"}
    assert {matched.value for matched in page.items[1].matched_by} == {"semantic"}


def test_an_index_without_words_searches_by_meaning_and_says_so() -> None:
    page = provider(FakeStore(words=False)).search(SearchRequest("kualitas"))

    assert page.items[0].evidence.ref == Ref.parse(f"doc:{DOC}#pasal-137/ayat-3")
    assert page.warnings == (NO_WORDS,)


def test_the_cursor_gives_the_next_page() -> None:
    first = provider().search(SearchRequest("batas", limit=1))
    second = provider().search(SearchRequest("batas", limit=1, cursor=first.cursor))

    assert [hit.rank for hit in second.items] == [2]
    assert second.items[0].evidence.ref == Ref.parse(f"doc:{DOC}#pasal-137/ayat-4")


def test_a_kind_filter_that_removes_everything_says_so() -> None:
    page = provider().search(SearchRequest("batas", kinds=frozenset({"fatwa"})))

    assert page.items == ()
    assert page.empty_reason.value == "filters_exclude_all"


def test_read_of_a_document_is_a_card() -> None:
    body = provider().read(Ref.parse(f"doc:{DOC}"))

    assert body.body is not None
    assert body.ref == Ref.parse(f"doc:{DOC}")


def test_read_of_an_address_we_do_not_hold_is_unknown_ref() -> None:
    with pytest.raises(UnknownRef):
        provider().read(Ref.parse(f"doc:{DOC}#pasal-999"))


def test_find_provision_resolves_a_citation() -> None:
    output = provider().call(FIND, {"citation": "POJK 40/2024 Pasal 137 ayat (3)"})

    assert output["items"][0]["ref"] == f"doc:{DOC}#pasal-137/ayat-3"
    assert output["items"][0]["citation"] == "POJK 40/2024, Pasal 137 ayat (3)"


def test_find_provision_of_a_document_outside_the_index_says_so() -> None:
    with pytest.raises(UnknownRef):
        provider().call(FIND, {"citation": "POJK 99/2099 Pasal 1"})


def test_an_unknown_tool_lists_the_real_one() -> None:
    with pytest.raises(UnknownTool):
        provider().call("search_everything", {})


def test_a_long_unit_is_shown_in_part_in_a_hit_and_whole_when_read() -> None:
    from dataclasses import replace

    from metamorph_regulation_retrieval.adapters.provider import HIT_CHARS, SHORTENED

    long = replace(PASSAGES[0], text="Ketentuan pendanaan. " * 1000)
    store = FakeStore()
    store._kept = lambda filters: [long]  # noqa: SLF001 - one long unit
    store.read = lambda document_id, address: long
    regulation = provider(store)

    hit = regulation.search(SearchRequest("pendanaan")).items[0]
    assert len(hit.evidence.body.wording) <= HIT_CHARS + 1 and hit.evidence.body.wording.endswith("…")
    assert regulation.search(SearchRequest("pendanaan")).warnings == (SHORTENED,)
    assert regulation.read(hit.evidence.ref).body.wording == long.text


def test_links_carry_their_ends_date_and_confidence() -> None:
    page = provider().links(Ref.parse(f"doc:{DOC}"), LinksRequest())

    assert page.items[0] == Link(LinkType.REVOKES, Ref.parse("doc:ojk:pojk:2025:1"), Ref.parse(f"doc:{DOC}"),
                                 effective_on=date(2025, 1, 1), confidence=0.9)
    assert page.items[1].source == Ref.parse("doc:ojk:pojk:2025:2#pasal-i")
    assert page.items[1].target == Ref.parse(f"doc:{DOC}#pasal-137/ayat-3")
    assert page.items[1].confidence == 0.6


def test_links_ask_the_store_for_the_direction_and_types_asked() -> None:
    store = FakeStore()

    provider(store).links(Ref.parse(f"doc:{DOC}#pasal-5"), LinksRequest(direction=Direction.INCOMING,
                                                                        types=frozenset({LinkType.AMENDS})))

    assert store.asked_links == (DOC, "pasal-5", True, False, ["amends"])


def test_links_page_by_offset() -> None:
    first = provider().links(Ref.parse(f"doc:{DOC}"), LinksRequest(limit=2))
    second = provider().links(Ref.parse(f"doc:{DOC}"), LinksRequest(limit=2, cursor=first.cursor))

    assert [link.type for link in first.items] == [LinkType.REVOKES, LinkType.AMENDS]
    assert [link.type for link in second.items] == [LinkType.LEGAL_BASIS]
    assert second.cursor is None


def test_a_ref_of_another_layer_has_no_regulation_links() -> None:
    page = provider().links(Ref.parse("report:ojk:lpksi:2025#p-1"), LinksRequest())

    assert page.items == () and page.empty_reason is EmptyReason.NO_MATCH


def test_a_regulation_not_published_can_still_be_asked_about() -> None:
    page = provider().links(Ref.parse("doc:ojk:pojk:2099:1"), LinksRequest())

    assert page.items  # a link may name a document that isn't published: never unknown_ref


def test_an_index_built_before_links_says_so() -> None:
    page = provider(FakeStore(linked=False)).links(Ref.parse(f"doc:{DOC}"), LinksRequest())

    assert page.items == () and page.warnings == (NO_LINKS,)


def test_a_document_shows_its_status_history() -> None:
    history = [{"status": "revoked", "effective_from": "2025-01-01", "source": "links"}]

    class Revoked(FakeStore):
        def document(self, document_id):
            return {**super().document(document_id), "status_history": history}

    evidence = provider(Revoked()).read(Ref.parse(f"doc:{DOC}"))

    assert evidence.body.fields["status_history"] == history


def test_every_link_type_is_ordered_but_the_markets() -> None:
    assert {*ORDER, LinkType.NAMES.value} == {link_type.value for link_type in LinkType}
