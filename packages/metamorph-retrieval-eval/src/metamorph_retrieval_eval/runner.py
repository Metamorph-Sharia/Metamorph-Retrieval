"""Running cases against a provider: each case's call made as the agent would make it, then judged.

Cases name the agent's tools. Three are the contract's own operations (search_documents, read, follow_links), and
the gateway serves them so; every other tool is the provider's, and returns a page of hits or of evidence. Anything
else a provider returns or raises is its fault, reported on the case, and the run goes on.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.codec import ContractViolation
from metamorph_retrieval_contract.errors import InvalidArgument, RetrievalError
from metamorph_retrieval_contract.evidence import Evidence, Figures, Record
from metamorph_retrieval_contract.provider import RetrievalProvider
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_eval.cases import Case
from metamorph_retrieval_eval.scoring import Outcome, Result, judge

SEARCH = "search_documents"
READ = "read"
FOLLOW_LINKS = "follow_links"


class MalformedOutput(Exception):
    """A provider's output that doesn't meet the contract."""


def run(provider: RetrievalProvider, cases: Sequence[Case]) -> tuple[Outcome, ...]:
    return tuple(judge(case, call(provider, case)) for case in cases)


def call(provider: RetrievalProvider, case: Case) -> Result:
    try:
        return _call(provider, case.tool, case.arguments)
    except RetrievalError as error:
        return Result(error=error.code, message=error.message)
    except ContractViolation as violation:  # the arguments: what an agent sending them would be told
        return Result(error="invalid_argument", message=str(violation))
    except MalformedOutput as malformed:
        return Result(error="malformed_output", message=str(malformed))
    except Exception as exc:  # noqa: BLE001 - a provider's crash is a finding, not the end of the run
        return Result(error="crashed", message=f"{type(exc).__name__}: {exc}")


def unheld(provider: RetrievalProvider, cases: Sequence[Case]) -> tuple[Ref, ...]:
    """Expected refs in the provider's namespaces that it doesn't hold: a case gone stale, or data missing."""
    manifest = provider.manifest()
    expected = dict.fromkeys(
        ref
        for case in cases
        for ref in (*case.expect.refs, *case.expect.names, *(figure.ref for figure in case.expect.figures))
        if manifest.owns(ref)
    )
    held = {card.ref for card in provider.describe(list(expected))}
    return tuple(ref for ref in expected if ref not in held)


def _call(provider: RetrievalProvider, tool: str, arguments: Mapping[str, Any]) -> Result:
    if tool == SEARCH:
        page = provider.search(codec.search_request_from_dict(arguments))
        return _result([hit.evidence for hit in page.items])
    if tool == READ:
        return _result([provider.read(_ref(arguments), window=arguments.get("window", 0))])
    if tool == FOLLOW_LINKS:
        asked = _ref(arguments)
        request = codec.links_request_from_dict({key: value for key, value in arguments.items() if key != "ref"})
        links = provider.links(asked, request).items
        return Result(refs=tuple(link.source if _is(link.target, asked) else link.target for link in links))
    return _result(_evidence_of(provider.call(tool, arguments)))


def _ref(arguments: Mapping[str, Any]) -> Ref:
    if not isinstance(arguments.get("ref"), str):
        raise InvalidArgument("ref: say which ref")
    return Ref.parse(arguments["ref"])


def _evidence_of(output: Mapping[str, Any]) -> list[Evidence]:
    """A tool's page: of hits for a ranked tool, of evidence for an exact one."""
    try:
        return [hit.evidence for hit in codec.hits_from_dict(output).items]
    except ContractViolation:
        pass
    try:
        return list(codec.evidence_page_from_dict(output).items)
    except ContractViolation as violation:
        raise MalformedOutput(f"not a page of hits or of evidence: {violation}") from None


def _result(evidence: Sequence[Evidence]) -> Result:
    return Result(
        refs=tuple(item.ref for item in evidence),
        names=frozenset(ref for item in evidence if isinstance(item.body, Record) for ref in _named(item.body.fields)),
        figures=tuple(
            (item.ref, observation)
            for item in evidence
            if isinstance(item.body, Figures)
            for observation in item.body.observations
        ),
    )


def _named(value: object) -> Iterator[Ref]:
    """Every `ref` a record's fields hold, however deep: what the evidence names, e.g. an industry's regulations."""
    if isinstance(value, Mapping):
        if isinstance(value.get("ref"), str):
            yield Ref.parse(value["ref"])
        for inner in value.values():
            yield from _named(inner)
    elif isinstance(value, list | tuple):
        for inner in value:
            yield from _named(inner)


def _is(end: Ref, asked: Ref) -> bool:
    return end == asked or (asked.address is None and end.whole() == asked)
