"""Does a provider keep the contract? `conformance_problems` says every way it doesn't; none means it does.

Any provider runs it in its own tests, with samples from what it holds:

    assert conformance_problems(MarketProvider(...), Samples(refs=(...), unknown=..., query="...")) == []

It checks what the gateway relies on: refs in the provider's own namespaces, `read` and `describe` agreeing,
unknown refs refused, limits kept, ranks from 1, the same call giving the same result, links and search present
exactly when the manifest says so, tools meeting their schemas, and everything readable on the wire.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeVar

from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.codec import ContractViolation
from metamorph_retrieval_contract.errors import CapabilityMissing, RetrievalError, UnknownRef, UnknownTool
from metamorph_retrieval_contract.evidence import Evidence
from metamorph_retrieval_contract.provider import CONTRACT_VERSION, Manifest, RetrievalProvider
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest
from metamorph_retrieval_contract.schema import json_problems

NO_SUCH_TOOL = "conformance_no_such_tool"
T = TypeVar("T")


@dataclass(frozen=True)
class ToolCall:
    tool: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class Samples:
    refs: tuple[Ref, ...]  # refs the provider holds
    unknown: Ref  # a well-formed ref in its namespaces that it doesn't hold
    query: str | None = None  # a query at least two of its pieces of evidence answer, when it has search
    linked: Ref | None = None  # a ref it knows links about, when it has links
    tool_calls: tuple[ToolCall, ...] = field(default=())  # at least one call of each of its tools


def conformance_problems(provider: RetrievalProvider, samples: Samples) -> list[str]:
    found = _Problems()
    manifest = found.run("manifest", provider.manifest)
    if manifest is None:
        return found.problems
    _check_samples(found, manifest, samples)
    _check_manifest(found, manifest)
    _check_reads(found, provider, manifest, samples)
    _check_search(found, provider, manifest, samples)
    _check_links(found, provider, manifest, samples)
    _check_tools(found, provider, manifest, samples)
    return found.problems


class _Problems:
    """Collects problems. A check that raises is one more problem, never the end of the run."""

    def __init__(self) -> None:
        self.problems: list[str] = []

    def add(self, problem: str) -> None:
        self.problems.append(problem)

    def run(self, what: str, call: Callable[[], T]) -> T | None:
        try:
            return call()
        except RetrievalError as error:
            self.add(f"{what}: raised {error.code}: {error.message}")
        except Exception as exc:  # noqa: BLE001 - a provider's crash is a finding
            self.add(f"{what}: raised {type(exc).__name__}: {exc}")
        return None

    def expect_error(
        self, what: str, error: type[RetrievalError], call: Callable[[], object], because: str | None = None
    ) -> None:
        try:
            call()
        except error:
            return
        except Exception as exc:  # noqa: BLE001
            self.add(f"{what}: raised {type(exc).__name__}: {exc}, not {error.code}")
            return
        self.add(f"{what}: didn't raise {error.code}" + (f": {because}" if because else ""))

    def repeatable(self, what: str, call: Callable[[], T], first: T) -> None:
        """The same call, the same result: what makes a provider testable and its results cacheable."""
        if self.run(what, call) != first:
            self.add(f"{what}: the same call gave a different result")

    def wire(self, what: str, value: T, read: Callable[[dict[str, Any]], T]) -> None:
        try:
            back = read(codec.to_dict(value))
        except ContractViolation as violation:
            self.add(f"{what}: not readable on the wire: {violation}")
            return
        if back != value:
            self.add(f"{what}: reads back differently from the wire")


def _check_samples(found: _Problems, manifest: Manifest, samples: Samples) -> None:
    if not samples.refs:
        found.add("samples: give at least one ref the provider holds")
    for ref in (*samples.refs, samples.unknown):
        if not manifest.owns(ref):
            found.add(f"samples: {ref} is not in the provider's namespaces")
    if manifest.kinds and samples.query is None:
        found.add("samples: the manifest lists kinds to search, so give a query")
    if manifest.links and samples.linked is None:
        found.add("samples: the manifest offers links, so give a linked ref")
    called = {call.tool for call in samples.tool_calls}
    for tool in manifest.tools:
        if tool.name not in called:
            found.add(f"samples: no call of the tool {tool.name}")


def _check_manifest(found: _Problems, manifest: Manifest) -> None:
    if manifest.contract_version != CONTRACT_VERSION:
        found.add(f"manifest: speaks {manifest.contract_version}, not {CONTRACT_VERSION}")
    found.wire("manifest", manifest, codec.manifest_from_dict)


def _check_reads(found: _Problems, provider: RetrievalProvider, manifest: Manifest, samples: Samples) -> None:
    held = [ref for ref in samples.refs if manifest.owns(ref)]
    cards = []
    for ref in held:
        evidence = found.run(f"read({ref})", lambda ref=ref: provider.read(ref))
        if evidence is None:
            continue
        if evidence.ref != ref:
            found.add(f"read({ref}): returned {evidence.ref}")
        found.repeatable(f"read({ref})", lambda ref=ref: provider.read(ref), evidence)
        found.wire(f"read({ref})", evidence, codec.evidence_from_dict)
        cards.append(evidence.card())
    found.expect_error(f"read({samples.unknown})", UnknownRef, lambda: provider.read(samples.unknown))
    described = found.run("describe", lambda: list(provider.describe([*held, samples.unknown])))
    if described is not None and described != cards:
        found.add("describe: should give read(ref).card() for each ref it holds, in the order asked, and leave out "
                  "the rest")


def _check_search(found: _Problems, provider: RetrievalProvider, manifest: Manifest, samples: Samples) -> None:
    if not manifest.kinds:
        found.expect_error("search", CapabilityMissing, lambda: provider.search(SearchRequest("conformance")),
                           because="the manifest lists no kinds")
        return
    if samples.query is None:
        return
    query = samples.query
    page = found.run("search", lambda: provider.search(SearchRequest(query)))
    if page is None:
        return
    one = found.run("search", lambda: provider.search(SearchRequest(query, limit=1)))
    if one is not None and len(one.items) > 1:
        found.add(f"search: {len(one.items)} hits for a limit of 1")
    ranks = [hit.rank for hit in page.items]
    if ranks != list(range(1, len(ranks) + 1)):
        found.add(f"search: ranks {ranks} don't run from 1")
    for hit in page.items:
        _check_held(found, "search", manifest, hit.evidence)
    found.repeatable("search", lambda: provider.search(SearchRequest(query)), page)
    found.wire("search", page, codec.hits_from_dict)


def _check_held(found: _Problems, what: str, manifest: Manifest, evidence: Evidence) -> None:
    if not manifest.owns(evidence.ref):
        found.add(f"{what}: {evidence.ref} is not in the provider's namespaces")
    elif evidence.kind not in manifest.kinds:
        found.add(f"{what}: kind {evidence.kind!r} is not one the manifest lists")


def _check_links(found: _Problems, provider: RetrievalProvider, manifest: Manifest, samples: Samples) -> None:
    if not manifest.links:
        ref = samples.linked or (samples.refs[0] if samples.refs else samples.unknown)
        found.expect_error("links", CapabilityMissing, lambda: provider.links(ref, LinksRequest()),
                           because="the manifest offers no links")
        return
    if samples.linked is None:
        return
    linked = samples.linked
    page = found.run("links", lambda: provider.links(linked, LinksRequest()))
    if page is None:
        return
    for link in page.items:
        if linked not in (link.source, link.target):
            found.add(f"links: a link of neither end {linked}: {link.source} {link.type} {link.target}")
    found.repeatable("links", lambda: provider.links(linked, LinksRequest()), page)
    found.wire("links", page, codec.links_from_dict)


def _check_tools(found: _Problems, provider: RetrievalProvider, manifest: Manifest, samples: Samples) -> None:
    tools = {tool.name: tool for tool in manifest.tools}
    for sample in samples.tool_calls:
        what = f"call({sample.tool})"
        if sample.tool not in tools:
            found.add(f"samples: no tool {sample.tool} in the manifest")
            continue
        for problem in json_problems(dict(sample.arguments), tools[sample.tool].input_schema):
            found.add(f"samples: {what} arguments: {problem}")
        output = found.run(what, lambda sample=sample: provider.call(sample.tool, sample.arguments))
        if output is None:
            continue
        for problem in json_problems(output, tools[sample.tool].output_schema):
            found.add(f"{what}: output: {problem}")
    found.expect_error(f"call({NO_SUCH_TOOL})", UnknownTool, lambda: provider.call(NO_SUCH_TOOL, {}))

