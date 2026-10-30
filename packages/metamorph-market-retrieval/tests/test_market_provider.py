from dataclasses import replace

import pytest
from market_samples import PUBLISHED_AT
from memory_index import ConceptEmbedder, MemoryIndex
from memory_market import MemoryMarket

from metamorph_market_retrieval.adapters.provider import MarketProvider
from metamorph_market_retrieval.domain.indexing import passage_unit
from metamorph_market_retrieval.domain.refs import NAMESPACES
from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.conformance import Samples, ToolCall, conformance_problems
from metamorph_retrieval_contract.errors import CapabilityMissing, InvalidArgument
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import SearchRequest

R = Ref.parse
SAMPLES = Samples(
    refs=(R("company:ojk:lpbbti:kep-21-d.05-2020"), R("series:bi:seki:tabel1_1:monthly:row=1"),
          R("report:ojk:roadmap:2023:lpbbti#p-43"), R("industry:ojk:portal:bank-umum-syariah"),
          R("sector:sharia-banking"), R("register:ojk:lpbbti")),
    unknown=R("report:ojk:lpksi:1999#p-1"),
    linked=R("company:ojk:lpbbti:kep-45-d.05-2019"),
    tool_calls=(
        ToolCall("find_companies", {"register": "ojk:lpbbti", "business_type": "sharia"}),
        ToolCall("find_companies", {"query": "Investree", "announcements": True}),
        ToolCall("find_companies", {"as_of": "2020-06-30"}),
        ToolCall("industry_context", {"query": "bank umum syariah"}),
        ToolCall("find_series", {"query": "uang beredar luas M2"}),
        ToolCall("get_observations", {"series": ["series:bi:seki:tabel1_1:monthly:row=1"], "from": "2026-07",
                                      "to": "2026-08"}),
    ),
)


def provider() -> MarketProvider:
    return MarketProvider(MemoryMarket())


def test_the_market_provider_keeps_the_retrieval_contract() -> None:
    assert conformance_problems(provider(), SAMPLES) == []


def test_its_manifest_owns_the_market_namespaces_offers_links_and_four_tools_and_no_search_yet() -> None:
    manifest = provider().manifest()

    assert (manifest.name, manifest.namespaces, manifest.kinds, manifest.links) == ("market", NAMESPACES, frozenset(),
                                                                                    True)
    assert [tool.name for tool in manifest.tools] == ["find_companies", "industry_context", "find_series",
                                                      "get_observations"]
    assert manifest.data_as_of == PUBLISHED_AT


def test_without_an_index_search_is_missing_and_says_why() -> None:
    with pytest.raises(CapabilityMissing, match="no index version is active"):
        provider().search(SearchRequest("pembiayaan"))


def test_a_tools_arguments_are_checked_against_its_schema_first() -> None:
    with pytest.raises(InvalidArgument) as caught:
        provider().call("find_companies", {"top_k": 5, "limit": 40})

    assert caught.value.message.startswith("find_companies: ")
    assert "'top_k' was unexpected" in caught.value.message
    assert "limit: 40 is greater than the maximum of 25" in caught.value.message
    with pytest.raises(InvalidArgument, match="as_of: '30 Juni 2020' is not a 'date'"):
        provider().call("find_companies", {"as_of": "30 Juni 2020"})


def test_a_tool_answers_with_the_contracts_pages() -> None:
    exact = provider().call("find_companies", {"register": "ojk:lpbbti"})
    ranked = provider().call("find_series", {"query": "uang beredar"})

    assert codec.evidence_page_from_dict(exact).items
    assert codec.hits_from_dict(ranked).items[0].rank == 1


def test_every_tool_description_says_its_evidence_never_binds() -> None:
    for tool in provider().manifest().tools:
        assert "never a requirement" in tool.description, tool.name


def indexed() -> MarketProvider:
    market = MemoryMarket()
    embedder = ConceptEmbedder()
    index = MemoryIndex([passage_unit(passage) for passage in market.all_passages], embedder)
    return MarketProvider(market, index=index, embedder=embedder, min_similarity=0.3)


def test_with_an_index_it_searches_report_and_release_passages_and_keeps_the_contract() -> None:
    provider = indexed()
    manifest = provider.manifest()

    assert (manifest.kinds, manifest.index_version) == (frozenset({"report", "release"}), "market-test.1")
    assert provider.search(SearchRequest("pembiayaan sektor produktif")).items[0].evidence.ref == R(
        "report:ojk:roadmap:2023:lpbbti#p-43")
    assert conformance_problems(provider, replace(SAMPLES, query="pembiayaan sektor produktif")) == []
