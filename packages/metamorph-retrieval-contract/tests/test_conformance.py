from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

import pytest
from memory_provider import MANIFEST, NAMES_POJK_40, POJK_40, MemoryProvider
from retrieval_samples import company, regulation, release_passage, report_passage

from metamorph_retrieval_contract.conformance import Samples, ToolCall, conformance_problems
from metamorph_retrieval_contract.errors import CapabilityMissing
from metamorph_retrieval_contract.evidence import Evidence, Hit, MatchedBy, Page
from metamorph_retrieval_contract.links import Link, LinkType
from metamorph_retrieval_contract.provider import JSON
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest

SAMPLES = Samples(
    refs=(report_passage().ref, release_passage().ref),
    unknown=Ref.parse("report:ojk:lpksi:1999#p-1"),
    query="fintech syariah ojk",  # both passages match: the report two words, the release one
    linked=POJK_40,
    tool_calls=(ToolCall("count", {"kind": "report"}),),
)


def problems_of(provider: object, samples: Samples = SAMPLES) -> list[str]:
    return conformance_problems(provider, samples)  # type: ignore[arg-type]


def test_a_provider_that_keeps_the_contract_has_no_problems() -> None:
    assert problems_of(MemoryProvider()) == []


def test_a_provider_without_search_or_links_conforms_when_its_manifest_says_so() -> None:
    provider = MemoryProvider(manifest=replace(MANIFEST, kinds=frozenset(), links=False))

    assert problems_of(provider, replace(SAMPLES, query=None, linked=None)) == []


def test_samples_must_cover_what_the_manifest_offers() -> None:
    assert problems_of(MemoryProvider(), replace(SAMPLES, query=None, linked=None, tool_calls=())) == [
        "samples: the manifest lists kinds to search, so give a query",
        "samples: the manifest offers links, so give a linked ref",
        "samples: no call of the tool count",
    ]


def test_a_sample_outside_the_providers_namespaces_is_reported() -> None:
    found = problems_of(MemoryProvider(), replace(SAMPLES, unknown=Ref.parse("doc:ojk:pojk:1999:1")))

    assert "samples: doc:ojk:pojk:1999:1 is not in the provider's namespaces" in found


class ReadsTheWrongRef(MemoryProvider):
    def read(self, ref: Ref, *, window: int = 0) -> Evidence:
        return super().read(report_passage().ref)


class DescribeRefusesWhatItDoesntHold(MemoryProvider):
    def describe(self, refs: Sequence[Ref]) -> Sequence[Evidence]:
        return [self.read(ref).card() for ref in refs]


class InventsWhatItDoesntHold(MemoryProvider):
    def read(self, ref: Ref, *, window: int = 0) -> Evidence:
        return self.evidence.get(ref) or replace(report_passage(), ref=ref)

    def describe(self, refs: Sequence[Ref]) -> Sequence[Evidence]:
        return [self.read(ref).card() for ref in refs]


class SearchIgnoresTheLimit(MemoryProvider):
    def search(self, request: SearchRequest) -> Page[Hit]:
        return super().search(replace(request, limit=25))


class SearchRanksFromTwo(MemoryProvider):
    def search(self, request: SearchRequest) -> Page[Hit]:
        page = super().search(request)
        return replace(page, items=tuple(replace(hit, rank=hit.rank + 1) for hit in page.items))


class SearchReturnsAnotherProvidersEvidence(MemoryProvider):
    def search(self, request: SearchRequest) -> Page[Hit]:
        return Page((Hit(regulation(), rank=1, score=1.0, matched_by=frozenset({MatchedBy.WORDS})),))


class SearchReturnsAKindItDoesntList(MemoryProvider):
    def search(self, request: SearchRequest) -> Page[Hit]:
        held = replace(company(), ref=Ref.parse("report:ojk:not-a-report"))
        return Page((Hit(held, rank=1, score=1.0, matched_by=frozenset({MatchedBy.WORDS})),))


class SearchChangesItsMind(MemoryProvider):
    calls = 0

    def search(self, request: SearchRequest) -> Page[Hit]:
        self.calls += 1
        page = super().search(request)
        return replace(page, items=tuple(replace(hit, score=hit.score + self.calls) for hit in page.items))


class LinksDeclaredButMissing(MemoryProvider):
    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        raise CapabilityMissing("no links after all")


class LinksAnswerAnotherRef(MemoryProvider):
    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        return Page((Link(LinkType.AMENDS, Ref.parse("doc:ojk:pojk:2025:3"), Ref.parse("doc:ojk:pojk:2023:10")),))


class ToolBreaksItsSchema(MemoryProvider):
    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
        return {"count": "two"}


class EveryToolExists(MemoryProvider):
    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON:
        return super().call("count", {"kind": "report"})


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        (ReadsTheWrongRef(), "read(release:ojk:siaran-pers:2026:"),
        (DescribeRefusesWhatItDoesntHold(), "describe: raised unknown_ref"),
        (InventsWhatItDoesntHold(), "read(report:ojk:lpksi:1999#p-1): didn't raise unknown_ref"),
        (SearchIgnoresTheLimit(), "search: 2 hits for a limit of 1"),
        (SearchRanksFromTwo(), "search: ranks [2, 3] don't run from 1"),
        (SearchReturnsAnotherProvidersEvidence(), "search: doc:ojk:pojk:2024:40 is not in the provider's namespaces"),
        (SearchReturnsAKindItDoesntList(), "search: kind 'company' is not one the manifest lists"),
        (SearchChangesItsMind(), "search: the same call gave a different result"),
        (LinksDeclaredButMissing(), "links: raised capability_missing"),
        (LinksAnswerAnotherRef(), "links: a link of neither end doc:ojk:pojk:2024:40"),
        (ToolBreaksItsSchema(), "call(count): output: count: 'two' is not of type 'integer'"),
        (EveryToolExists(), "call(conformance_no_such_tool): didn't raise unknown_tool"),
    ],
    ids=lambda value: type(value).__name__ if isinstance(value, MemoryProvider) else "",
)
def test_each_way_of_breaking_the_contract_is_named(provider: MemoryProvider, expected: str) -> None:
    found = problems_of(provider)

    assert any(problem.startswith(expected) for problem in found), found


def test_a_provider_declaring_no_links_must_refuse_them() -> None:
    class AnswersLinksAnyway(MemoryProvider):
        def links(self, ref: Ref, request: LinksRequest) -> Page[Link]:
            return Page((NAMES_POJK_40,))

    provider = AnswersLinksAnyway(manifest=replace(MANIFEST, links=False))

    assert problems_of(provider, replace(SAMPLES, linked=None)) == [
        "links: didn't raise capability_missing: the manifest offers no links"
    ]


def test_a_manifest_of_another_contract_version_is_reported() -> None:
    provider = MemoryProvider(manifest=replace(MANIFEST, contract_version="retrieval-9.0"))

    assert problems_of(provider) == ["manifest: speaks retrieval-9.0, not retrieval-0.1"]


def test_a_check_that_crashes_is_a_problem_not_a_crash() -> None:
    class SearchCrashes(MemoryProvider):
        def search(self, request: SearchRequest) -> Page[Hit]:
            raise RuntimeError("index offline")

    assert "search: raised RuntimeError: index offline" in problems_of(SearchCrashes())
