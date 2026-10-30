from datetime import UTC, datetime

import pytest
from fakes import POJK_40, SHARIA_LENDING, UNPUBLISHED, Industries, Regulations, renamed
from memory_provider import MemoryProvider
from retrieval_samples import regulation, release_passage, report_passage

from metamorph_retrieval_contract.conformance import Samples, ToolCall, conformance_problems
from metamorph_retrieval_contract.errors import CapabilityMissing, UnknownRef, UnknownTool
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest
from metamorph_retrieval_gateway.application.gateway import Gateway


def gateway(*providers: object, **options: object) -> Gateway:
    return Gateway(providers or (MemoryProvider(), Regulations(), Industries()), **options)  # type: ignore[arg-type]


def test_a_ref_is_read_from_the_provider_owning_its_namespace() -> None:
    assert gateway().read(POJK_40) == regulation()
    assert gateway().read(report_passage().ref) == report_passage()


def test_a_ref_no_provider_owns_says_which_namespaces_there_are() -> None:
    with pytest.raises(UnknownRef, match="no provider owns fatwa: refs; the namespaces are doc, industry, release, "
                                         "report"):
        gateway().read(Ref.parse("fatwa:dsnmui:117"))


def test_two_providers_never_own_one_namespace_or_one_tool() -> None:
    with pytest.raises(ValueError, match="doc: owned by regulation and copy"):
        gateway(Regulations(), renamed(Regulations(), "copy"))
    with pytest.raises(ValueError, match="industry_context: offered by industries and copy"):
        gateway(Industries(), renamed(Industries(), "copy", namespaces=frozenset({"sector"})))


def test_a_tool_is_called_on_the_provider_offering_it() -> None:
    assert gateway().call("count", {"kind": "report"}) == {"count": 1}


def test_a_tool_no_provider_offers_names_the_tools_there_are() -> None:
    with pytest.raises(UnknownTool, match="no tool find_series; the tools are count, industry_context"):
        gateway().call("find_series", {})


def test_describe_asks_each_owner_once_and_keeps_the_order_asked() -> None:
    regulations = Regulations()
    asked = [report_passage().ref, POJK_40, Ref.parse("fatwa:dsnmui:117"), UNPUBLISHED, release_passage().ref]

    cards = gateway(MemoryProvider(), regulations).describe(asked)

    assert [card.ref for card in cards] == [report_passage().ref, POJK_40, release_passage().ref]
    assert regulations.described == [[POJK_40, UNPUBLISHED]]


def test_links_come_from_the_provider_answering_links() -> None:
    page = gateway().links(POJK_40, LinksRequest())

    assert [str(link.source) for link in page.items] == [str(release_passage().ref)]


def test_without_a_provider_answering_links_links_are_missing() -> None:
    with pytest.raises(CapabilityMissing, match="no provider answers links"):
        gateway(Regulations(), Industries()).links(POJK_40, LinksRequest())


def test_a_search_goes_to_the_provider_holding_the_kinds_asked() -> None:
    page = gateway().search(SearchRequest("fintech syariah", kinds=frozenset({"report"})))

    assert [hit.evidence.ref for hit in page.items] == [report_passage().ref]


def test_a_search_for_kinds_no_provider_holds_says_which_it_can_search() -> None:
    with pytest.raises(CapabilityMissing, match="no provider searches regulation; the kinds searched are release, "
                                                "report"):
        gateway().search(SearchRequest("pendanaan", kinds=frozenset({"regulation"})))
    with pytest.raises(CapabilityMissing, match="no provider searches yet"):
        gateway(Regulations()).search(SearchRequest("pendanaan"))


def test_its_manifest_is_the_providers_together() -> None:
    manifest = gateway().manifest()

    assert manifest.name == "gateway"
    assert manifest.namespaces == {"report", "release", "doc", "industry"}
    assert manifest.kinds == {"report", "release"}
    assert manifest.links is True
    assert [tool.name for tool in manifest.tools] == ["count", "industry_context"]
    assert manifest.index_version == "industries:industries-1 memory:memory-1 regulation:published-sql"


def test_its_data_is_as_old_as_its_oldest_provider() -> None:
    older = renamed(Regulations(), "regulation", data_as_of=datetime(2026, 1, 1, tzinfo=UTC))

    assert gateway(MemoryProvider(), older).manifest().data_as_of == datetime(2026, 1, 1, tzinfo=UTC)


def test_a_ref_in_an_industry_is_routed_too() -> None:
    assert gateway().read(SHARIA_LENDING).ref == SHARIA_LENDING


def test_the_gateway_keeps_the_retrieval_contract() -> None:
    samples = Samples(
        refs=(report_passage().ref, release_passage().ref, POJK_40, SHARIA_LENDING),
        unknown=Ref.parse("doc:ojk:pojk:1999:1"),
        query="fintech syariah ojk",
        linked=POJK_40,
        tool_calls=(ToolCall("count", {"kind": "report"}), ToolCall("industry_context", {})),
    )

    assert conformance_problems(gateway(), samples) == []
