"""The market provider, as the retrieval contract has it: a manifest, search, reading, links and four tools.

Search over report and release passages needs an index version (built by `metamorph-market-index`). Without one the
manifest lists no kinds to search, and search says so.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from metamorph_market_retrieval.adapters.tools import market_tools
from metamorph_market_retrieval.application.links import NamedBy
from metamorph_market_retrieval.application.ports import Embedder, MarketReadModel, SearchIndex
from metamorph_market_retrieval.application.reading import Reading
from metamorph_market_retrieval.application.search import PASSAGE_KINDS, Meaning, SearchPassages
from metamorph_market_retrieval.domain.evidence import INDEX_VERSION, PROVIDER
from metamorph_market_retrieval.domain.refs import NAMESPACES
from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.errors import CapabilityMissing, UnknownTool
from metamorph_retrieval_contract.evidence import Evidence, Hit, Page
from metamorph_retrieval_contract.links import Link
from metamorph_retrieval_contract.provider import JSON, Manifest
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest

VERSION = "0.1.0"


class MarketProvider:
    def __init__(self, read_model: MarketReadModel, *, index: SearchIndex | None = None,
                 embedder: Embedder | None = None, min_similarity: float = 0.0) -> None:
        self.read_model = read_model
        self.index = index
        self.reading = Reading(read_model)
        self.named_by = NamedBy(read_model)
        by_meaning = index is not None and index.model is not None and embedder is not None
        meaning = Meaning(index, embedder, min_similarity=min_similarity) if by_meaning else None
        self.tools = market_tools(read_model, meaning)
        self.searching = SearchPassages(read_model, index, meaning) if index else None

    def manifest(self) -> Manifest:
        return Manifest(
            name=PROVIDER,
            version=VERSION,
            namespaces=NAMESPACES,
            kinds=PASSAGE_KINDS if self.index else frozenset(),
            links=True,
            tools=tuple(tool.spec for tool in self.tools.values()),
            index_version=self.index.version if self.index else INDEX_VERSION,
            data_as_of=self.read_model.published_at(),
        )

    def search(self, request: SearchRequest) -> Page[Hit]:
        if self.searching is None:
            raise CapabilityMissing("market: no index version is active, so reports and releases can't be searched; "
                                    "find_companies, find_series and industry_context still answer, or read a ref")
        return self.searching.run(request)

    def read(self, ref: Ref, *, window: int = 0) -> Evidence:
        return self.reading.read(ref, window=window)

    def describe(self, refs: Sequence[Ref]) -> Sequence[Evidence]:
        return self.reading.describe(refs)

    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        return self.named_by.run(ref, request)

    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
        if tool not in self.tools:
            raise UnknownTool(f"market has no tool {tool}; its tools: {', '.join(self.tools)}")
        return codec.to_dict(self.tools[tool].run(arguments))
