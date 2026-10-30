from dataclasses import replace

import pytest
from retrieval_samples import PUBLISHED_AT

from metamorph_retrieval_contract.provider import CONTRACT_VERSION, Manifest, ToolSpec
from metamorph_retrieval_contract.refs import Ref

OBJECT = {"type": "object"}


def find_series() -> ToolSpec:
    return ToolSpec(
        name="find_series",
        version="0.1",
        description="Which statistics measure this? Datasets first, then their series by label.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        output_schema=OBJECT,
    )


def market_manifest() -> Manifest:
    return Manifest(
        name="market",
        version="0.1.0",
        namespaces=frozenset({"report", "release", "dataset", "series", "company"}),
        kinds=frozenset({"report", "release"}),
        links=True,
        tools=(find_series(),),
        index_version="market-2026-10-30.1",
        data_as_of=PUBLISHED_AT,
    )


def test_a_manifest_speaks_this_contract_version_unless_it_says_otherwise() -> None:
    assert market_manifest().contract_version == CONTRACT_VERSION == "retrieval-0.1"


def test_a_provider_owns_the_refs_in_its_namespaces() -> None:
    manifest = market_manifest()

    assert manifest.owns(Ref.parse("report:ojk:lpksi:2025#p-12"))
    assert not manifest.owns(Ref.parse("doc:ojk:pojk:2024:40"))


def test_a_manifest_names_each_tool_once() -> None:
    with pytest.raises(ValueError, match="tools: find_series twice"):
        replace(market_manifest(), tools=(find_series(), find_series()))


def test_a_manifest_owns_at_least_one_namespace_and_names_it_as_refs_do() -> None:
    with pytest.raises(ValueError, match="namespaces: a provider owns at least one"):
        replace(market_manifest(), namespaces=frozenset())
    with pytest.raises(ValueError, match="namespaces: 'Series' is not"):
        replace(market_manifest(), namespaces=frozenset({"Series"}))


def test_a_tool_is_named_for_an_agent_and_its_schemas_are_json_schemas() -> None:
    with pytest.raises(ValueError, match="'find series' is not a tool name"):
        replace(find_series(), name="find series")
    with pytest.raises(ValueError, match="input_schema"):
        replace(find_series(), input_schema={"type": "no such type"})
