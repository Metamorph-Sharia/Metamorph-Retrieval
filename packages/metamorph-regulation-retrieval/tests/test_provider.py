from datetime import UTC, datetime

import pytest

from metamorph_regulation_retrieval.adapters.provider import FIND, RegulationProvider
from metamorph_regulation_retrieval.domain.passage import Passage
from metamorph_retrieval_contract.conformance import Samples, ToolCall, conformance_problems
from metamorph_retrieval_contract.errors import CapabilityMissing, UnknownRef, UnknownTool
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


class FakeStore:
    def search(self, vector, limit):
        return [(passage, 0.8 - index / 100) for index, passage in enumerate(PASSAGES[:limit])]

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


def provider() -> RegulationProvider:
    return RegulationProvider(FakeStore(), FakeEmbedder())


SAMPLES = Samples(
    refs=(Ref.parse(f"doc:{DOC}#pasal-137/ayat-3"), Ref.parse(f"doc:{DOC}#pasal-137/ayat-4")),
    unknown=Ref.parse("doc:ojk:pojk:2099:1"),
    query="batas maksimum pemberian pendanaan",
    tool_calls=(ToolCall(FIND, {"citation": "POJK 40/2024 Pasal 137 ayat (3)"}),),
)


def test_the_regulatory_provider_keeps_the_retrieval_contract() -> None:
    assert conformance_problems(provider(), SAMPLES) == []


def test_it_owns_doc_refs_and_offers_exact_lookup() -> None:
    manifest = provider().manifest()

    assert manifest.namespaces == frozenset({"doc"})
    assert "fatwa" in manifest.kinds
    assert manifest.links is False
    assert [tool.name for tool in manifest.tools] == [FIND]


def test_search_returns_ranked_evidence() -> None:
    page = provider().search(SearchRequest("batas pendanaan", limit=2))

    assert [item.rank for item in page.items] == [1, 2]
    assert page.items[0].evidence.ref == Ref.parse(f"doc:{DOC}#pasal-137/ayat-3")
    assert page.items[0].evidence.legal_force.value == "binding"


def test_search_warns_about_filters_it_cannot_apply() -> None:
    page = provider().search(SearchRequest("batas", documents=(Ref.parse(f"doc:{DOC}"),), sort=Sort.NEWEST))

    assert any("documents" in warning for warning in page.warnings)
    assert any("sort" in warning for warning in page.warnings)


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


def test_links_are_capability_missing() -> None:
    with pytest.raises(CapabilityMissing):
        provider().links(Ref.parse(f"doc:{DOC}#pasal-137/ayat-3"), LinksRequest())
