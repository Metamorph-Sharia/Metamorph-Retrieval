import fake_service
import httpx
import pytest
from fake_service import BASE

from metamorph_regulation_retrieval.adapters.provider import RegulationProvider
from metamorph_retrieval_contract.conformance import Samples, ToolCall, conformance_problems
from metamorph_retrieval_contract.errors import CapabilityMissing, ProviderUnavailable, UnknownRef
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest, Sort

R = Ref.parse
SAMPLES = Samples(
    refs=(R(f"{BASE}#pasal-137/ayat-3"), R(f"{BASE}#pasal-137/ayat-4")),
    unknown=R("doc:ojk:pojk:2099:1"),
    query="batas maksimum pemberian pendanaan",
    tool_calls=(ToolCall("find_provision", {"citation": "POJK 40/2024 Pasal 137 ayat (3)"}),),
)


def provider(client: httpx.Client | None = None) -> RegulationProvider:
    return RegulationProvider("http://rag", client=client or fake_service.client())


def test_the_regulatory_provider_keeps_the_retrieval_contract() -> None:
    assert conformance_problems(provider(), SAMPLES) == []


def test_it_owns_doc_refs_and_offers_search() -> None:
    manifest = provider().manifest()

    assert manifest.namespaces == frozenset({"doc"})
    assert "regulation" in manifest.kinds
    assert "fatwa" in manifest.kinds
    assert manifest.links is False
    assert [tool.name for tool in manifest.tools] == ["find_provision"]
    assert manifest.index_version == "bench_emb_r2p_full_bge_m3"


def test_search_carries_the_filters_it_can_apply() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(__import__("json").loads(request.content))
        return fake_service.handle(request)

    client = httpx.Client(base_url="http://rag", transport=httpx.MockTransport(handler))
    provider(client).search(SearchRequest("batas", kinds=frozenset({"regulation"}), issuers=frozenset({"ojk"})))

    assert seen["kinds"] == ["regulation"]
    assert seen["issuers"] == ["ojk"]


def test_a_filter_it_cannot_apply_is_a_warning_not_a_silent_widening() -> None:
    page = provider().search(SearchRequest("batas", documents=(R(BASE),), sort=Sort.NEWEST))

    assert any("documents" in warning for warning in page.warnings)
    assert any("sort" in warning for warning in page.warnings)


def test_read_of_a_ref_it_does_not_hold_is_unknown_ref() -> None:
    with pytest.raises(UnknownRef):
        provider().read(R("doc:ojk:pojk:2099:1"))


def test_links_are_capability_missing_until_the_platform_serves_them() -> None:
    with pytest.raises(CapabilityMissing):
        provider().links(R(f"{BASE}#pasal-137/ayat-3"), LinksRequest())


def test_a_service_that_is_down_is_provider_unavailable() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = httpx.Client(base_url="http://rag", transport=httpx.MockTransport(down))
    with pytest.raises(ProviderUnavailable):
        provider(client).search(SearchRequest("batas"))


def test_find_provision_is_our_own_tool() -> None:
    page = provider().call("find_provision", {"citation": "POJK 40/2024 Pasal 137 ayat (3)"})

    assert page["items"][0]["ref"] == f"{BASE}#pasal-137/ayat-3"
