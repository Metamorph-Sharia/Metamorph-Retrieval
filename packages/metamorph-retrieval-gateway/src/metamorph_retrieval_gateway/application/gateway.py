"""The gateway: the providers together, as one provider. It knows them only by their manifests.

A ref goes to the provider owning its namespace, a tool to the provider offering it, a search to the provider
holding the kinds asked. What a record names by ref, its owner cites (enrichment.py). Nothing here knows about
markets or regulations, so a new provider, or a new tool, needs no change here: it is joined in the wiring.

Every call to a provider has a time budget. A provider that is late or crashes is `provider_unavailable`, saying
which; its own errors (an unknown ref, a bad argument) reach the caller as they are. A late provider's work isn't
stopped, only no longer awaited: each provider bounds its own work too (the market's statement timeout).

A search that several providers can answer goes to each of them at once, and their rankings are fused by reciprocal
rank (fusion.py): a provider's scores mean nothing to another's, its ranks do. A provider that fails leaves the others'
answer and a warning. Links go to every provider answering them, whoever owns the ref, and are merged in turn, the
owner's first.

With a reranker (reranking.py), every search's candidates, each provider's first ones fused, are put in the
reranker's order, which holds across providers as ranks don't. A reranker that fails or is late leaves the fused
order, with a warning: reranking improves a search, it never stops one.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
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
from metamorph_retrieval_contract.evidence import EmptyReason, Evidence, Hit, Page, Record
from metamorph_retrieval_contract.links import Link
from metamorph_retrieval_contract.provider import JSON, Manifest, RetrievalProvider
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import MAX_LIMIT, LinksRequest, SearchRequest
from metamorph_retrieval_gateway.application.calls import timed
from metamorph_retrieval_gateway.application.enrichment import MAX_NAMED, card_fields, cited, named, past_budget
from metamorph_retrieval_gateway.application.fusion import fuse, fused_page, merged_page, offset_of, ranked_page
from metamorph_retrieval_gateway.application.reranking import CANDIDATES, NOT_RERANKED, RERANK, Reranker, rerank_text
from metamorph_retrieval_gateway.application.reranking import TIMEOUT as RERANK_TIMEOUT

T = TypeVar("T")

NAME = "gateway"
VERSION = "0.1.0"
TIMEOUT = 10.0  # seconds a provider has to answer one call
WORKERS = 16


class Gateway:
    def __init__(self, providers: Sequence[RetrievalProvider], *, timeout: float = TIMEOUT,
                 reranker: Reranker | None = None, candidates: int = CANDIDATES,
                 rerank_timeout: float = RERANK_TIMEOUT) -> None:
        self.providers = {provider.manifest().name: provider for provider in providers}
        self.joined = {name: provider.manifest() for name, provider in self.providers.items()}  # what each offers
        self.owners = _one_each("owned", {name: manifest.namespaces for name, manifest in self.joined.items()})
        self.tools = _one_each("offered", {name: {tool.name for tool in manifest.tools}
                                           for name, manifest in self.joined.items()})
        self.timeout = timeout
        self.reranker, self.candidates, self.rerank_timeout = reranker, candidates, rerank_timeout
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
        asked_of = {name: kinds & asked for name, kinds in holders.items() if kinds & asked}
        if self.reranker is not None:
            return self._reranked(request, asked_of)
        if len(asked_of) == 1:
            ((name, kinds),) = asked_of.items()
            return self._ask(name, lambda: self.providers[name].search(replace(request, kinds=kinds)))
        return self._federated(request, asked_of)

    def _federated(self, request: SearchRequest, asked_of: Mapping[str, frozenset[str]]) -> Page[Hit]:
        """Each provider's first pages, fused, and the slice the cursor asks for."""
        start = offset_of(request.cursor)
        enough = min(start + request.limit, MAX_LIMIT)
        pages, warnings, why_empty = self._gathered({name: (lambda name=name, kinds=kinds: self.providers[name].search(
            replace(request, kinds=kinds, limit=enough, cursor=None))) for name, kinds in asked_of.items()})
        return fused_page([pages[name] for name in sorted(pages)], start=start, limit=request.limit,
                          warnings=warnings, why_empty=why_empty)

    def _reranked(self, request: SearchRequest, asked_of: Mapping[str, frozenset[str]]) -> Page[Hit]:
        """Each provider's first candidates, fused, then in the reranker's order; the slice the cursor asks for."""
        start = offset_of(request.cursor)
        pages, warnings, why_empty = self._gathered({name: (lambda name=name, kinds=kinds: self._candidates(
            name, replace(request, kinds=kinds, cursor=None))) for name, kinds in asked_of.items()})
        fused = fuse([pages[name] for name in sorted(pages)])[: self.candidates]
        hits = [hit for hit, _ in fused]
        try:
            texts = [rerank_text(hit.evidence) for hit in hits]
            scores = self.workers.submit(timed(RERANK, lambda: self.reranker.scores(  # type: ignore[union-attr]
                request.query, texts)))
            ranked = sorted(zip(hits, (float(score) for score in scores.result(timeout=self.rerank_timeout)),
                                strict=True), key=lambda pair: -pair[1])
        except Exception:  # noqa: BLE001 - late or failed, the fused order stands
            ranked, warnings = fused, (*warnings, NOT_RERANKED)
        return ranked_page(ranked, start=start, limit=request.limit, warnings=warnings, why_empty=why_empty)

    def _candidates(self, name: str, request: SearchRequest) -> Page[Hit]:
        return _first(self.candidates, lambda cursor: self.providers[name].search(
            replace(request, limit=MAX_LIMIT, cursor=cursor)))

    def _gathered(self, questions: Mapping[str, Callable[[], Page[Any]]]) -> tuple[dict[str, Page[Any]],
                                                                                   tuple[str, ...], EmptyReason]:
        """Each provider's page, asked at once; their warnings, each named; and why they'd be empty together. A
        provider that fails is a warning while another answered with hits."""
        answers = self._ask_each(questions)
        pages = {name: answer for name, answer in answers.items() if isinstance(answer, Page)}
        failed = {name: answer for name, answer in answers.items() if not isinstance(answer, Page)}
        if not pages:
            raise next(iter(failed.values()))
        warnings = [f"{name}: {warning}" for name, page in sorted(pages.items()) for warning in page.warnings]
        warnings += [f"{name}: {error.message}" for name, error in sorted(failed.items())]
        if failed and not any(page.items for page in pages.values()):
            raise next(iter(failed.values()))  # nothing found by those that answered says nothing about the rest
        reasons = {page.empty_reason for page in pages.values() if not page.items}
        why_empty = EmptyReason.FILTERS_EXCLUDE_ALL if reasons == {EmptyReason.FILTERS_EXCLUDE_ALL} \
            else EmptyReason.NO_MATCH
        return pages, tuple(warnings), why_empty

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
        owner = self.owners.get(ref.namespace)
        linking = sorted((name for name, manifest in self.joined.items() if manifest.links),
                         key=lambda name: (name != owner, name))
        if not linking:
            raise CapabilityMissing("no provider answers links yet")
        if len(linking) == 1:
            return self._ask(linking[0], lambda: self.providers[linking[0]].links(ref, request))
        start = offset_of(request.cursor)
        enough = start + request.limit + 1  # one more, to know whether a next page exists
        pages, warnings, why_empty = self._gathered(
            {name: (lambda name=name: self._first_links(name, ref, request, enough)) for name in linking})
        return merged_page([pages[name] for name in linking if name in pages], start=start, limit=request.limit,
                           warnings=warnings, why_empty=why_empty)

    def _first_links(self, name: str, ref: Ref, request: LinksRequest, count: int) -> Page[Link]:
        return _first(count, lambda cursor: self.providers[name].links(
            ref, replace(request, limit=MAX_LIMIT, cursor=cursor)))

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
        return self._answer(name, self.workers.submit(timed(name, question)))

    def _ask_each(self, questions: Mapping[str, Callable[[], T]]) -> dict[str, T | ProviderUnavailable]:
        """Several providers at once, each within the time budget: each one's answer, or why it gave none."""
        asked = {name: self.workers.submit(timed(name, question)) for name, question in questions.items()}
        answers: dict[str, T | ProviderUnavailable] = {}
        for name, answer in asked.items():
            try:
                answers[name] = self._answer(name, answer)
            except ProviderUnavailable as unavailable:
                answers[name] = unavailable
        return answers

    def _answer(self, name: str, answer: Future[T]) -> T:
        try:
            return answer.result(timeout=self.timeout)
        except Late:
            raise ProviderUnavailable(f"{name} didn't answer within {self.timeout:g} s; try again later") from None
        except RetrievalError:
            raise
        except Exception as exc:  # noqa: BLE001 - its internals (a connection string, a query) stay in the logs
            raise ProviderUnavailable(f"{name} failed ({type(exc).__name__}); try again later") from exc


def _first(count: int, ask: Callable[[str | None], Page[T]]) -> Page[T]:
    """A provider's first `count` items, over as many pages as that takes."""
    page = ask(None)
    items, warnings = list(page.items), list(page.warnings)
    while page.cursor is not None and len(items) < count:
        page = ask(page.cursor)
        items += page.items
        warnings += [warning for warning in page.warnings if warning not in warnings]
    if not items:
        return Page.empty(page.empty_reason or EmptyReason.NO_MATCH, tuple(warnings))
    return Page(tuple(items[:count]), warnings=tuple(warnings))


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
