"""The gateway, as a retrieval provider over HTTP: what an agent's own code, or the evaluation runner, holds.

    METAMORPH_RETRIEVAL_GATEWAY_URL=http://localhost:8765 \\
        uv run metamorph-eval run eval/market/cases.jsonl --provider metamorph_retrieval_gateway.client:from_environment

Errors come back as the contract's types. An agent framework speaks MCP to /mcp instead; this is for Python code.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.codec import ContractViolation
from metamorph_retrieval_contract.errors import ProviderUnavailable
from metamorph_retrieval_contract.evidence import Evidence, Hit, Page
from metamorph_retrieval_contract.links import Link
from metamorph_retrieval_contract.provider import JSON, Manifest
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest

GATEWAY_URL = "METAMORPH_RETRIEVAL_GATEWAY_URL"
TIMEOUT = 30.0


class RetrievalClient:
    def __init__(self, http: httpx.Client) -> None:
        self.http = http

    @classmethod
    def at(cls, url: str, *, timeout: float = TIMEOUT) -> RetrievalClient:
        return cls(httpx.Client(base_url=url, timeout=timeout))

    def manifest(self) -> Manifest:
        return codec.manifest_from_dict(self._answer("GET", "/manifest"))

    def search(self, request: SearchRequest) -> Page[Hit]:
        return codec.hits_from_dict(self.call("search_documents", codec.to_dict(request)))

    def read(self, ref: Ref, *, window: int = 0) -> Evidence:
        return codec.evidence_from_dict(self.call("read", {"ref": str(ref), "window": window}))

    def describe(self, refs: Sequence[Ref]) -> Sequence[Evidence]:
        cards = self._answer("POST", "/describe", {"refs": [str(ref) for ref in refs]})
        return [codec.evidence_from_dict(card) for card in cards["items"]]

    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        return codec.links_from_dict(self.call("follow_links", {"ref": str(ref), **codec.to_dict(request)}))

    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
        return self._answer("POST", f"/tools/{tool}", dict(arguments))

    def _answer(self, method: str, path: str, body: JSON | None = None) -> JSON:
        try:
            response = self.http.request(method, path, json=body)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"the gateway didn't answer: {exc}") from None
        if response.is_success:
            return response.json()
        try:
            raise codec.error_from_dict(response.json())
        except (ContractViolation, ValueError):
            raise ProviderUnavailable(f"the gateway answered {response.status_code}") from None


def from_environment() -> RetrievalClient:
    url = os.environ.get(GATEWAY_URL)
    if not url:
        raise ValueError(f"set {GATEWAY_URL} to the gateway's address, e.g. http://localhost:8765")
    return RetrievalClient.at(url)
