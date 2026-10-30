"""The contract's types ⇄ JSON values, as MCP, HTTP and a remote provider carry them.

Reading checks the shape's JSON Schema first, then builds the types, whose own checks may still refuse what the
schema allows (an empty page without a reason). Either way the caller gets one ContractViolation listing why.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime
from functools import singledispatch
from typing import Any, TypeVar

from metamorph_retrieval_contract.errors import ERRORS, InvalidArgument, RetrievalError
from metamorph_retrieval_contract.evidence import (
    Body,
    EmptyReason,
    Evidence,
    Figures,
    Hit,
    LegalForce,
    MatchedBy,
    Observation,
    Page,
    PageSpan,
    Provenance,
    Qualifiers,
    Record,
    Text,
)
from metamorph_retrieval_contract.links import Direction, Link, LinkType
from metamorph_retrieval_contract.provider import JSON, Manifest, ToolSpec
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import DEFAULT_LIMIT, LinksRequest, SearchRequest, Sort
from metamorph_retrieval_contract.schema import schema_problems

T = TypeVar("T")


class ContractViolation(Exception):
    """Data that doesn't meet the retrieval contract. `problems` lists every reason found.

    Not a RetrievalError: whoever reads decides what it means. An agent's bad arguments are its invalid_argument;
    a provider's bad answer is that provider's fault.
    """

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


# Writing


@singledispatch
def to_dict(value: object) -> JSON:
    raise TypeError(f"{type(value).__name__} is not a shape of the retrieval contract")


@to_dict.register
def _(evidence: Evidence) -> JSON:
    return {
        "ref": str(evidence.ref),
        "kind": evidence.kind,
        "citation": evidence.citation,
        "title": evidence.title,
        "legal_force": evidence.legal_force.value,
        "qualifiers": _qualifiers(evidence.qualifiers),
        "published_on": _day(evidence.published_on),
        "url": evidence.url,
        "body": _body(evidence.body),
        "provenance": {
            "provider": evidence.provenance.provider,
            "index_version": evidence.provenance.index_version,
            "source_published_at": evidence.provenance.source_published_at.isoformat(),
        },
    }


@to_dict.register
def _(hit: Hit) -> JSON:
    return {
        "rank": hit.rank,
        "score": hit.score,
        "matched_by": sorted(match.value for match in hit.matched_by),
        "evidence": to_dict(hit.evidence),
    }


@to_dict.register
def _(link: Link) -> JSON:
    return {
        "type": link.type.value,
        "source": str(link.source),
        "target": str(link.target),
        "effective_on": _day(link.effective_on),
        "confidence": link.confidence,
    }


@to_dict.register
def _(page: Page) -> JSON:
    return {
        "items": [to_dict(item) for item in page.items],
        "cursor": page.cursor,
        "empty_reason": page.empty_reason.value if page.empty_reason else None,
        "warnings": list(page.warnings),
    }


@to_dict.register
def _(request: SearchRequest) -> JSON:
    return {
        "query": request.query,
        "kinds": sorted(request.kinds),
        "issuers": sorted(request.issuers),
        "documents": [str(ref) for ref in request.documents],
        "published_from": _day(request.published_from),
        "published_to": _day(request.published_to),
        "in_force_on": _day(request.in_force_on),
        "legal_force": sorted(force.value for force in request.legal_force),
        "sort": request.sort.value,
        "limit": request.limit,
        "cursor": request.cursor,
    }


@to_dict.register
def _(request: LinksRequest) -> JSON:
    return {
        "direction": request.direction.value,
        "types": sorted(link_type.value for link_type in request.types),
        "limit": request.limit,
        "cursor": request.cursor,
    }


@to_dict.register
def _(manifest: Manifest) -> JSON:
    return {
        "name": manifest.name,
        "version": manifest.version,
        "contract_version": manifest.contract_version,
        "namespaces": sorted(manifest.namespaces),
        "kinds": sorted(manifest.kinds),
        "links": manifest.links,
        "tools": [
            {
                "name": tool.name,
                "version": tool.version,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
            }
            for tool in manifest.tools
        ],
        "index_version": manifest.index_version,
        "data_as_of": manifest.data_as_of.isoformat() if manifest.data_as_of else None,
    }


@to_dict.register
def _(error: RetrievalError) -> JSON:
    return {"error": error.code, "message": error.message}


# Reading


def evidence_from_dict(data: Mapping[str, Any]) -> Evidence:
    return _read(data, "evidence", _evidence)


def hits_from_dict(data: Mapping[str, Any]) -> Page[Hit]:
    return _read(data, "hit_page", lambda page: _page(page, _hit))


def evidence_page_from_dict(data: Mapping[str, Any]) -> Page[Evidence]:
    return _read(data, "evidence_page", lambda page: _page(page, _evidence))


def links_from_dict(data: Mapping[str, Any]) -> Page[Link]:
    return _read(data, "link_page", lambda page: _page(page, _link))


def search_request_from_dict(data: Mapping[str, Any]) -> SearchRequest:
    return _read(data, "search_request", _search_request)


def links_request_from_dict(data: Mapping[str, Any]) -> LinksRequest:
    return _read(data, "links_request", _links_request)


def manifest_from_dict(data: Mapping[str, Any]) -> Manifest:
    return _read(data, "manifest", _manifest)


def error_from_dict(data: Mapping[str, Any]) -> RetrievalError:
    return _read(data, "error", lambda error: ERRORS[error["error"]](error["message"]))


def _read(data: Mapping[str, Any], shape: str, build: Callable[[Mapping[str, Any]], T]) -> T:
    found = schema_problems(data, shape)
    if found:
        raise ContractViolation(found)
    try:
        return build(data)
    except (ValueError, InvalidArgument) as exc:
        raise ContractViolation([str(exc)]) from None


def _evidence(data: Mapping[str, Any]) -> Evidence:
    provenance = data["provenance"]
    return Evidence(
        ref=Ref.parse(data["ref"]),
        kind=data["kind"],
        citation=data["citation"],
        title=data["title"],
        legal_force=LegalForce(data["legal_force"]),
        qualifiers=Qualifiers(
            status=data["qualifiers"]["status"],
            valid_from=_date(data["qualifiers"]["valid_from"]),
            valid_to=_date(data["qualifiers"]["valid_to"]),
            under_review=data["qualifiers"]["under_review"],
            provisional=data["qualifiers"]["provisional"],
            as_of=_date(data["qualifiers"]["as_of"]),
        ),
        published_on=_date(data["published_on"]),
        url=data["url"],
        body=_read_body(data["body"]),
        provenance=Provenance(
            provider=provenance["provider"],
            index_version=provenance["index_version"],
            source_published_at=datetime.fromisoformat(provenance["source_published_at"]),
        ),
    )


def _read_body(data: Mapping[str, Any] | None) -> Body | None:
    if data is None:
        return None
    if data["type"] == "text":
        pages = data["pages"]
        return Text(data["wording"], PageSpan(pages["start"], pages["end"]) if pages else None)
    if data["type"] == "figures":
        observations = tuple(
            Observation(item["period"], item["value"], item["provisional"]) for item in data["observations"]
        )
        return Figures(data["unit"], data["frequency"], observations)
    return Record(data["fields"])


def _hit(data: Mapping[str, Any]) -> Hit:
    return Hit(
        evidence=_evidence(data["evidence"]),
        rank=data["rank"],
        score=data["score"],
        matched_by=frozenset(MatchedBy(match) for match in data["matched_by"]),
    )


def _link(data: Mapping[str, Any]) -> Link:
    return Link(
        type=LinkType(data["type"]),
        source=Ref.parse(data["source"]),
        target=Ref.parse(data["target"]),
        effective_on=_date(data["effective_on"]),
        confidence=data["confidence"],
    )


def _page(data: Mapping[str, Any], item: Callable[[Mapping[str, Any]], T]) -> Page[T]:
    reason = data["empty_reason"]
    return Page(
        items=tuple(item(entry) for entry in data["items"]),
        cursor=data["cursor"],
        empty_reason=EmptyReason(reason) if reason else None,
        warnings=tuple(data["warnings"]),
    )


def _search_request(data: Mapping[str, Any]) -> SearchRequest:
    return SearchRequest(
        query=data["query"],
        kinds=frozenset(data.get("kinds", ())),
        issuers=frozenset(data.get("issuers", ())),
        documents=tuple(Ref.parse(ref) for ref in data.get("documents", ())),
        published_from=_date(data.get("published_from")),
        published_to=_date(data.get("published_to")),
        in_force_on=_date(data.get("in_force_on")),
        legal_force=frozenset(LegalForce(force) for force in data.get("legal_force", ())),
        sort=Sort(data.get("sort", Sort.RELEVANCE)),
        limit=data.get("limit", DEFAULT_LIMIT),
        cursor=data.get("cursor"),
    )


def _links_request(data: Mapping[str, Any]) -> LinksRequest:
    return LinksRequest(
        direction=Direction(data.get("direction", Direction.BOTH)),
        types=frozenset(LinkType(link_type) for link_type in data.get("types", ())),
        limit=data.get("limit", DEFAULT_LIMIT),
        cursor=data.get("cursor"),
    )


def _manifest(data: Mapping[str, Any]) -> Manifest:
    return Manifest(
        name=data["name"],
        version=data["version"],
        contract_version=data["contract_version"],
        namespaces=frozenset(data["namespaces"]),
        kinds=frozenset(data["kinds"]),
        links=data["links"],
        tools=tuple(ToolSpec(**tool) for tool in data["tools"]),
        index_version=data["index_version"],
        data_as_of=datetime.fromisoformat(data["data_as_of"]) if data["data_as_of"] else None,
    )


def _qualifiers(qualifiers: Qualifiers) -> JSON:
    return {
        "status": qualifiers.status,
        "valid_from": _day(qualifiers.valid_from),
        "valid_to": _day(qualifiers.valid_to),
        "under_review": qualifiers.under_review,
        "provisional": qualifiers.provisional,
        "as_of": _day(qualifiers.as_of),
    }


def _body(body: Body | None) -> JSON | None:
    if body is None:
        return None
    if isinstance(body, Text):
        pages = {"start": body.pages.start, "end": body.pages.end} if body.pages else None
        return {"type": "text", "wording": body.wording, "pages": pages}
    if isinstance(body, Figures):
        return {
            "type": "figures",
            "unit": body.unit,
            "frequency": body.frequency,
            "observations": [
                {"period": item.period, "value": item.value, "provisional": item.provisional}
                for item in body.observations
            ],
        }
    return {"type": "record", "fields": dict(body.fields)}


def _day(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
