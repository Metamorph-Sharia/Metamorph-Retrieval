"""The gateway: the providers together, as one provider. It knows them only by their manifests.

A ref goes to the provider owning its namespace, a tool to the provider offering it, a search to the provider
holding the kinds asked. What a record names by ref, its owner cites (enrichment.py). Nothing here knows about
markets or regulations, so a new provider, or a new tool, needs no change here: it is joined in the wiring.

Every call to a provider has a time budget. A provider that is late or crashes is `provider_unavailable`, saying
which; its own errors (an unknown ref, a bad argument) reach the caller as they are. A late provider's work isn't
stopped, only no longer awaited: each provider bounds its own work too (the market's statement timeout).

Merging several providers' searches or links (reciprocal rank fusion) waits for a second provider that searches or
links (M5). Until then each goes to the one provider that offers it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as Late
from dataclasses import replace
from typing import Any, TypeVar

from metamorph_retrieval_contract.errors import (
    CapabilityMissing,
    ProviderUnavailable,
    RetrievalError,
    UnknownRef,
    UnknownTool,
)
from metamorph_retrieval_contract.evidence import Evidence, Hit, Page, Record
from metamorph_retrieval_contract.links import Link
from metamorph_retrieval_contract.provider import JSON, Manifest, RetrievalProvider
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest
from metamorph_retrieval_gateway.application.enrichment import MAX_NAMED, card_fields, cited, named, past_budget

T = TypeVar("T")

NAME = "gateway"
VERSION = "0.1.0"
TIMEOUT = 10.0  # seconds a provider has to answer one call
WORKERS = 16


class Gateway:
    def __init__(self, providers: Sequence[RetrievalProvider], *, timeout: float = TIMEOUT) -> None:
        self.providers = {provider.manifest().name: provider for provider in providers}
        self.joined = {name: provider.manifest() for name, provider in self.providers.items()}  # what each offers
        self.owners = _one_each("owned", {name: manifest.namespaces for name, manifest in self.joined.items()})
        self.tools = _one_each("offered", {name: {tool.name for tool in manifest.tools}
                                           for name, manifest in self.joined.items()})
        self.timeout = timeout
        self.workers = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="provider")

    def manifest(self) -> Manifest:
        manifests = sorted((self._ask(name, provider.manifest) for name, provider in self.providers.items()),
                           key=lambda manifest: manifest.name)
        as_of = [manifest.data_as_of for manifest in manifests if manifest.data_as_of]
        return Manifest(
            name=NAME,
            version=VERSION,
            namespaces=frozenset().union(*(manifest.namespaces for manifest in manifests)),
            kinds=frozenset().union(*(manifest.kinds for manifest in manifests)),
            links=any(manifest.links for manifest in manifests),
            tools=tuple(sorted((tool for manifest in manifests for tool in manifest.tools), key=lambda t: t.name)),
            index_version=" ".join(f"{manifest.name}:{manifest.index_version}" for manifest in manifests),
            data_as_of=min(as_of) if as_of else None,
        )

    def search(self, request: SearchRequest) -> Page[Hit]:
        holders = {name: manifest.kinds for name, manifest in self.joined.items()}
        searchable = sorted(set().union(*holders.values()))
        if not searchable:
            raise CapabilityMissing("no provider searches yet; read a ref, or use a tool")
        asked = request.kinds or frozenset(searchable)
        unheld = sorted(asked - set(searchable))
        if unheld:
            raise CapabilityMissing(f"no provider searches {', '.join(unheld)}; the kinds searched are "
                                    f"{', '.join(searchable)}")
        (name,) = [name for name, kinds in holders.items() if kinds & asked]  # one until M5
        return self._ask(name, lambda: self.providers[name].search(replace(request, kinds=asked)))

    def read(self, ref: Ref, *, window: int = 0) -> Evidence:
        name = self._owner(ref)
        evidence = self._ask(name, lambda: self.providers[name].read(ref, window=window))
        if not isinstance(evidence.body, Record):
            return evidence
        fields, _ = self._cited(evidence.body.fields, name)  # a warning has no place on one piece of evidence
        return replace(evidence, body=Record(fields))

    def describe(self, refs: Sequence[Ref]) -> Sequence[Evidence]:
        cards = {card.ref: card for name, owned in _by_owner(refs, self.owners).items()
                 for card in self._ask(name, lambda name=name, owned=owned: self.providers[name].describe(owned))}
        return [cards[ref] for ref in refs if ref in cards]

    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        linking = [name for name, manifest in self.joined.items() if manifest.links]
        if not linking:
            raise CapabilityMissing("no provider answers links yet")
        (name,) = linking  # one until M5
        return self._ask(name, lambda: self.providers[name].links(ref, request))

    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
        if tool not in self.tools:
            raise UnknownTool(f"no tool {tool}; the tools are {', '.join(sorted(self.tools))}")
        name = self.tools[tool]
        output = self._ask(name, lambda: self.providers[name].call(tool, arguments))
        if not isinstance(output.get("items"), list):
            return output
        records = [_record_fields(item) for item in output["items"]]
        fields, warnings = self._cited([found for found in records if found is not None], name)
        rest = iter(fields)
        items = [_with_fields(item, next(rest)) if found is not None else item
                 for item, found in zip(output["items"], records, strict=True)]
        return output | {"items": items, "warnings": [*output.get("warnings", ()), *warnings]}

    def _cited(self, value: Any, answered_by: str) -> tuple[Any, list[str]]:
        """The value with each ref its stubs name cited by its owner, and what couldn't be. Only refs another
        provider owns: those the answering provider couldn't cite itself."""
        refs = list(dict.fromkeys(ref for ref in named(value)
                                  if ref.namespace in self.owners and self.owners[ref.namespace] != answered_by))
        warnings = [past_budget(len(refs) - MAX_NAMED)] if len(refs) > MAX_NAMED else []
        cards: dict[str, Any] = {}
        for name, owned in _by_owner(refs[:MAX_NAMED], self.owners).items():
            try:
                found = self._ask(name, lambda name=name, owned=owned: self.providers[name].describe(owned))
            except ProviderUnavailable as unavailable:
                warnings.append(f"named refs without citations: {unavailable.message}")
                continue
            cards |= {str(card.ref): card_fields(card) for card in found}
        return cited(value, cards), warnings

    def _owner(self, ref: Ref) -> str:
        if ref.namespace not in self.owners:
            raise UnknownRef(f"no provider owns {ref.namespace}: refs; the namespaces are "
                             f"{', '.join(sorted(self.owners))}")
        return self.owners[ref.namespace]

    def _ask(self, name: str, question: Callable[[], T]) -> T:
        """One call to one provider, within the time budget."""
        answer = self.workers.submit(question)
        try:
            return answer.result(timeout=self.timeout)
        except Late:
            raise ProviderUnavailable(f"{name} didn't answer within {self.timeout:g} s; try again later") from None
        except RetrievalError:
            raise
        except Exception as exc:  # noqa: BLE001 - its internals (a connection string, a query) stay in the logs
            raise ProviderUnavailable(f"{name} failed ({type(exc).__name__}); try again later") from exc


def _record_fields(item: JSON) -> JSON | None:
    """A page item's record fields: a hit's evidence's, or the evidence's own."""
    body = item.get("evidence", item).get("body")
    return body["fields"] if isinstance(body, Mapping) and body.get("type") == "record" else None


def _with_fields(item: JSON, fields: JSON) -> JSON:
    if "evidence" in item:
        return item | {"evidence": _with_fields(item["evidence"], fields)}
    return item | {"body": item["body"] | {"fields": fields}}


def _by_owner(refs: Sequence[Ref], owners: Mapping[str, str]) -> dict[str, list[Ref]]:
    asked: dict[str, list[Ref]] = {}
    for ref in dict.fromkeys(refs):
        if ref.namespace in owners:
            asked.setdefault(owners[ref.namespace], []).append(ref)
    return asked


def _one_each(verb: str, claims: Mapping[str, set[str] | frozenset[str]]) -> dict[str, str]:
    """Each name claimed (a namespace, a tool) and the one provider claiming it."""
    claimed: dict[str, str] = {}
    for provider, names in claims.items():
        for name in sorted(names):
            if name in claimed:
                raise ValueError(f"{name}: {verb} by {claimed[name]} and {provider}")
            claimed[name] = provider
    return claimed
