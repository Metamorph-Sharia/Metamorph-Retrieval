"""The regulatory provider: our retrieval service, spoken through the contract.

The index, the embedding model and the clause ranking stay in the regulation retrieval service; this adapter is the
provider the gateway composes. It maps requests and errors, and nothing else. That keeps one copy of the retrieval
logic and one set of shapes, and it lets the gateway stay a composition layer rather than a search engine.

Search and read are the contract's operations, so they are not declared again as tools. `find_provision` is ours: an
exact citation lookup ("POJK 40/2024 Pasal 137 ayat (3)") that a similarity search cannot do reliably.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import httpx

from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.errors import (
    CapabilityMissing,
    InvalidArgument,
    ProviderUnavailable,
    RetrievalError,
    UnknownRef,
    UnknownTool,
)
from metamorph_retrieval_contract.evidence import Evidence, Hit, Page
from metamorph_retrieval_contract.links import Link
from metamorph_retrieval_contract.provider import JSON, Manifest, ToolSpec
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest, Sort

NAME = "regulation-retrieval"
VERSION = "0.1.0"
SEARCH = "search_regulations"
READ = "read_regulation"
FIND = "find_provision"
DEFAULT_TIMEOUT = 10.0

ERRORS: dict[str, type[RetrievalError]] = {
    "invalid_argument": InvalidArgument,
    "unknown_ref": UnknownRef,
    "unknown_tool": UnknownTool,
    "capability_missing": CapabilityMissing,
    "provider_unavailable": ProviderUnavailable,
}


class RegulationProvider:
    """The retrieval service as a provider. One HTTP client, one cached manifest."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = client or httpx.Client(base_url=base_url, headers=headers, timeout=timeout)
        self._manifest: Manifest | None = None

    # -- what it offers ---------------------------------------------------

    def manifest(self) -> Manifest:
        if self._manifest is None:
            data = self._get("/manifest")
            self._manifest = Manifest(
                name=data["name"],
                version=data["version"],
                namespaces=frozenset(data["namespaces"]),
                kinds=frozenset(data["kinds"]),
                links=bool(data.get("links")),
                tools=_own_tools(data.get("tools") or ()),
                index_version=data["index_version"],
                data_as_of=_datetime(data.get("data_as_of")),
            )
        return self._manifest

    def search(self, request: SearchRequest) -> Page[Hit]:
        arguments: JSON = {"query": request.query, "limit": request.limit}
        warnings: list[str] = []

        if request.kinds:
            arguments["kinds"] = sorted(request.kinds)
        if request.issuers:
            arguments["issuers"] = sorted(request.issuers)
        if request.in_force_on:
            arguments["in_force_on"] = request.in_force_on.isoformat()
        if request.documents:
            warnings.append("documents: not applied; this provider searches the whole corpus, so narrow with in_force_on or kinds")
        if request.published_from or request.published_to:
            warnings.append("published_from/published_to: not applied; validity is filtered with in_force_on")
        if request.legal_force:
            warnings.append("legal_force: not applied; filter on kinds instead (fatwa is sharia, regulation is binding)")
        if request.sort is not Sort.RELEVANCE:
            warnings.append("sort: newest is not offered; results are ranked by relevance")

        page = codec.hits_from_dict(self._post(f"/tools/{SEARCH}", arguments))
        return replace(page, warnings=tuple(page.warnings) + tuple(warnings))

    def read(self, ref: Ref, *, window: int = 0) -> Evidence:
        return codec.evidence_from_dict(self._post(f"/tools/{READ}", {"ref": str(ref), "window": window}))

    def describe(self, refs: Sequence[Ref]) -> Sequence[Evidence]:
        cards: dict[Ref, Evidence] = {}
        for ref in refs:
            try:
                cards[ref] = self.read(ref).card()
            except UnknownRef:
                continue
        return [cards[ref] for ref in refs if ref in cards]

    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        raise CapabilityMissing("links between regulations are not served yet; the platform publishes them and a later "
                                "version of this provider will answer them")

    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
        if tool == FIND:
            return self._post(f"/tools/{FIND}", dict(arguments))
        raise UnknownTool(f"{NAME} has no tool {tool!r}; it offers {FIND}")

    # -- transport --------------------------------------------------------

    def _get(self, path: str) -> JSON:
        try:
            return self._answer(self._client.get(path))
        except httpx.HTTPError as error:
            raise ProviderUnavailable(f"{NAME} did not answer: {error}") from error

    def _post(self, path: str, body: Mapping[str, Any]) -> JSON:
        try:
            return self._answer(self._client.post(path, json=dict(body)))
        except httpx.HTTPError as error:
            raise ProviderUnavailable(f"{NAME} did not answer: {error}") from error

    def _answer(self, response: httpx.Response) -> JSON:
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            raise _error(response) from error
        except httpx.HTTPError as error:
            raise ProviderUnavailable(f"{NAME} did not answer: {error}") from error
        except ValueError as error:
            raise ProviderUnavailable(f"{NAME} answered with something that is not JSON") from error


def _error(response: httpx.Response) -> RetrievalError:
    try:
        body = response.json()
    except ValueError:
        return ProviderUnavailable(f"{NAME} failed with HTTP {response.status_code}")
    code = str(body.get("error") or "")
    message = str(body.get("message") or f"HTTP {response.status_code}")
    return ERRORS.get(code, ProviderUnavailable)(message)


def _own_tools(declared: Sequence[Mapping[str, Any]]) -> tuple[ToolSpec, ...]:
    """Only the tools we add. Search and read are the contract's operations and the gateway already serves them."""
    return tuple(
        ToolSpec(
            name=tool["name"],
            version=tool["version"],
            description=tool["description"],
            input_schema=tool["input_schema"],
            output_schema=tool["output_schema"],
        )
        for tool in declared
        if tool["name"] == FIND
    )


def _datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    return datetime.fromisoformat(str(value))
