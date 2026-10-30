import pytest
from memory_regulations import MemoryRegulations
from standin_samples import PUBLISHED_AT

from metamorph_regulation_standin.adapters.provider import StandinProvider
from metamorph_retrieval_contract.conformance import Samples, conformance_problems
from metamorph_retrieval_contract.errors import CapabilityMissing, UnknownTool
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest

R = Ref.parse
SAMPLES = Samples(
    refs=(R("doc:ojk:pojk:2024:40"), R("doc:ojk:pojk:2024:40#pasal-5/ayat-1"), R("doc:dsnmui:fatwa:117"),
          R("doc:dsnmui:fatwa:117#diktum-kedua/angka-1")),
    unknown=R("doc:ojk:pojk:2099:1"),
)


def provider() -> StandinProvider:
    return StandinProvider(MemoryRegulations())


def test_the_standin_keeps_the_retrieval_contract() -> None:
    assert conformance_problems(provider(), SAMPLES) == []


def test_it_owns_doc_refs_and_offers_reading_only() -> None:
    manifest = provider().manifest()

    assert (manifest.name, manifest.namespaces, manifest.kinds, manifest.links, manifest.tools) == (
        "regulation-standin", frozenset({"doc"}), frozenset(), False, ())
    assert manifest.data_as_of == PUBLISHED_AT


def test_search_links_and_tools_are_the_regulatory_providers_and_it_says_so() -> None:
    with pytest.raises(CapabilityMissing, match="regulations can be read and described by ref, not searched, until "
                                                "the regulatory provider joins"):
        provider().search(SearchRequest("pendanaan"))
    with pytest.raises(CapabilityMissing, match="links between regulations arrive with the regulatory provider"):
        provider().links(R("doc:ojk:pojk:2024:40"), LinksRequest())
    with pytest.raises(UnknownTool):
        provider().call("find_regulations", {})
