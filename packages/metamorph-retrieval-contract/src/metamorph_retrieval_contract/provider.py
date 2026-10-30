"""The provider protocol: what every retrieval provider offers, whoever builds it and whatever index it keeps.

The gateway knows providers only through this protocol and their manifests. It routes a ref to the provider that
owns its namespace, sends a search to those that hold the kinds asked for, and builds the agent's tool catalog from
the manifests' tools. So a new provider, or a new tool, needs no change in the gateway.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from jsonschema import Draft202012Validator, SchemaError

from metamorph_retrieval_contract.evidence import Evidence, Hit, Page
from metamorph_retrieval_contract.links import Link
from metamorph_retrieval_contract.refs import NAMESPACE, Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest

CONTRACT_VERSION = "retrieval-0.1"
TOOL_NAME = re.compile(r"[a-z][a-z0-9_]*")

JSON = dict[str, Any]


@dataclass(frozen=True)
class ToolSpec:
    """A provider's own tool. For an agent, the description is all it reads: say what it is for and when to use it."""

    name: str
    version: str  # a breaking change to either schema is a new version, served beside the old one
    description: str
    input_schema: JSON
    output_schema: JSON

    def __post_init__(self) -> None:
        if not TOOL_NAME.fullmatch(self.name):
            raise ValueError(f"{self.name!r} is not a tool name, such as find_series")
        for name, schema in (("input_schema", self.input_schema), ("output_schema", self.output_schema)):
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                raise ValueError(f"{self.name}.{name}: {exc.message}") from None


@dataclass(frozen=True)
class Manifest:
    name: str
    version: str
    namespaces: frozenset[str]  # the refs it owns; no two providers own one namespace
    kinds: frozenset[str]  # what its search holds; empty when it has no search
    links: bool  # whether it answers links()
    tools: tuple[ToolSpec, ...]
    index_version: str
    data_as_of: datetime | None  # the newest publish its index was built from
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not self.namespaces:
            raise ValueError("namespaces: a provider owns at least one")
        for namespace in sorted(self.namespaces):
            if not NAMESPACE.fullmatch(namespace):
                raise ValueError(f"namespaces: {namespace!r} is not a namespace, such as doc")
        names = [tool.name for tool in self.tools]
        twice = sorted({name for name in names if names.count(name) > 1})
        if twice:
            raise ValueError(f"tools: {', '.join(twice)} twice")

    def owns(self, ref: Ref) -> bool:
        return ref.namespace in self.namespaces


class RetrievalProvider(Protocol):
    def manifest(self) -> Manifest: ...

    def search(self, request: SearchRequest) -> Page[Hit]:
        """Over the kinds the manifest lists. A filter it can't apply to its kinds is noted in the page's warnings."""
        ...

    def read(self, ref: Ref, *, window: int = 0) -> Evidence:
        """The whole evidence; `window` passages either side of a passage. Raises UnknownRef."""
        ...

    def describe(self, refs: Sequence[Ref]) -> Sequence[Evidence]:
        """Cards, in the order asked, for the refs it owns and holds. Others are left out, never an error: a link may
        name a regulation that isn't published yet."""
        ...

    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        """What it knows about a ref, owned or not. Raises CapabilityMissing when the manifest says it has no links."""
        ...

    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
        """One of its own tools; the result meets the tool's output schema. Raises UnknownTool."""
        ...
