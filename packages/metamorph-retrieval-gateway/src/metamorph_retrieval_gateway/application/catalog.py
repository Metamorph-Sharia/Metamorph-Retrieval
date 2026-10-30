"""The agent's catalog: what MCP and HTTP serve. The contract's operations become three tools (search_documents,
read, follow_links), listed only when a provider offers them; every provider's own tools follow, as they declare
them. Descriptions and schemas stay byte-stable within a version, which also keeps an agent's prompt cache warm.

Each call is checked against its tool's input schema first, so an agent is told every problem at once. Its answer
must fit the size budget, so one call never floods the agent's context. Each call, answered or failed, is recorded.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.codec import ContractViolation
from metamorph_retrieval_contract.errors import InvalidArgument, RetrievalError, UnknownTool
from metamorph_retrieval_contract.provider import JSON, RetrievalProvider, ToolSpec
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.schema import json_problems, load_schema, shape_schema
from metamorph_retrieval_gateway.application.calls import TRACE, Call, CallLog, NoCallLog

SEARCH = "search_documents"
READ = "read"
FOLLOW_LINKS = "follow_links"
OPERATIONS = (SEARCH, READ, FOLLOW_LINKS)
VERSION = "0.1"
MAX_ANSWER_BYTES = 100_000  # about 25,000 tokens

logger = logging.getLogger(__name__)


class Catalog:
    def __init__(self, provider: RetrievalProvider, *, calls: CallLog | None = None,
                 max_answer_bytes: int = MAX_ANSWER_BYTES) -> None:
        self.provider = provider
        self.calls = calls or NoCallLog()
        self.max_answer_bytes = max_answer_bytes
        manifest = provider.manifest()
        operations = [*([_search(sorted(manifest.kinds))] if manifest.kinds else []), READ_TOOL,
                      *([FOLLOW_LINKS_TOOL] if manifest.links else [])]
        for tool in manifest.tools:
            if tool.name in OPERATIONS:
                raise ValueError(f"{tool.name}: a provider's tool can't take an operation's name")
        self.listed = {tool.name: tool for tool in (*operations, *manifest.tools)}

    def tools(self) -> tuple[ToolSpec, ...]:
        return tuple(self.listed.values())

    def run(self, name: str, arguments: Mapping[str, Any]) -> JSON:
        started_at, began = datetime.now(UTC), time.perf_counter()
        try:
            output = self._answer(name, arguments)
        except RetrievalError as error:
            self._record(Call(**_call(name, arguments, started_at, began), error=error.code, message=error.message))
            raise
        self._record(Call(**_call(name, arguments, started_at, began), **_summary(output)))
        return output

    def _answer(self, name: str, arguments: Mapping[str, Any]) -> JSON:
        if name in OPERATIONS and name not in self.listed:
            return _operation(self.provider, name, arguments)  # the provider says why it isn't offered
        if name not in self.listed:
            raise UnknownTool(f"no tool {name}; the tools are {', '.join(self.listed)}")
        problems = json_problems(dict(arguments), self.listed[name].input_schema)
        if problems:
            raise InvalidArgument(f"{name}: {'; '.join(problems)}")
        output = _operation(self.provider, name, arguments)
        size = len(json.dumps(output, ensure_ascii=False).encode())
        if size > self.max_answer_bytes:
            raise InvalidArgument(f"{name}: the answer is {size:,} bytes, over the {self.max_answer_bytes:,} one call "
                                  "may return; ask for less: a lower limit, fewer series, a shorter period or window")
        return output

    def _record(self, call: Call) -> None:
        try:
            self.calls.record(call)
        except Exception:  # noqa: BLE001 - losing a log line never costs the agent its answer
            logger.exception("call %s to %s not recorded", call.id, call.tool)


def _operation(provider: RetrievalProvider, name: str, arguments: Mapping[str, Any]) -> JSON:
    try:
        if name == SEARCH:
            return codec.to_dict(provider.search(codec.search_request_from_dict(arguments)))
        if name == READ:
            return codec.to_dict(provider.read(Ref.parse(arguments["ref"]), window=arguments.get("window", 0)))
        if name == FOLLOW_LINKS:
            request = codec.links_request_from_dict({key: value for key, value in arguments.items() if key != "ref"})
            return codec.to_dict(provider.links(Ref.parse(arguments["ref"]), request))
    except ContractViolation as violation:  # arguments the schema allows and the contract's types refuse
        raise InvalidArgument(f"{name}: {violation}") from None
    return provider.call(name, arguments)


def _call(name: str, arguments: Mapping[str, Any], started_at: datetime, began: float) -> dict[str, Any]:
    return {"id": uuid.uuid4().hex, "tool": name, "arguments": dict(arguments), "trace": TRACE.get(),
            "started_at": started_at, "duration_ms": (time.perf_counter() - began) * 1000}


def _summary(output: JSON) -> dict[str, Any]:
    """What came back: refs in order, a ranked tool's scores, the index builds that answered."""
    items = output["items"] if isinstance(output.get("items"), list) else [output] if "provenance" in output else []
    evidence = [item.get("evidence", item) for item in items if "provenance" in item.get("evidence", item)]
    links = [item for item in items if "source" in item and "target" in item]
    return {
        "refs": tuple(dict.fromkeys([*(item["ref"] for item in evidence),
                                     *(end for link in links for end in (link["source"], link["target"]))])),
        "scores": tuple(item["score"] for item in items if "score" in item),
        "index_versions": tuple(sorted({item["provenance"]["index_version"] for item in evidence})),
        "empty_reason": output.get("empty_reason"),
        "warnings": tuple(output.get("warnings", ())),
    }


def _schema(properties: dict[str, Any], required: list[str]) -> JSON:
    schema = load_schema()
    return {"$schema": schema["$schema"], "type": "object", "additionalProperties": False, "required": required,
            "properties": properties, "$defs": schema["$defs"]}


REF = {"$ref": "#/$defs/ref"}

READ_TOOL = ToolSpec(
    name=READ,
    version=VERSION,
    description=(
        "Read one ref in full: a report's or a release's passage, a company, a register, a dataset, a series, an "
        "industry, a sector, or a regulation or one of its provisions (doc:ojk:pojk:2024:40#pasal-5/ayat-1). Use it on "
        "any ref another tool returned, to quote it or to check what it says. For a passage, window gives that many "
        "passages either side. Returns one piece of evidence: its citation, to quote as it is; legal_force (binding: "
        "laws and regulations; sharia: DSN-MUI fatwas; explanatory; none: reports, releases, statistics and "
        "companies, which report or count and never require); qualifiers (status, validity, provisional, as_of); and "
        "its body: text, figures or a record. A record's refs to other evidence come with their citations."
    ),
    input_schema=_schema({"ref": REF, "window": {"type": "integer", "minimum": 0, "default": 0,
                                                 "description": "Passages either side of a passage"}}, ["ref"]),
    output_schema=shape_schema("evidence"),
)

FOLLOW_LINKS_TOOL = ToolSpec(
    name=FOLLOW_LINKS,
    version=VERSION,
    description=(
        "What a ref is linked to, and by what. For a regulation (doc:…), the report and release passages that name "
        "it; for a passage, the regulations and companies it names (type names). Use it to go from a regulation to "
        "what OJK or BI said about it, or from an announcement to the rules and companies it concerns. direction: "
        "incoming (what links to the ref), outgoing (what the ref links to), or both. Returns links: type, source and "
        "target refs, to read. Links between regulations (amends, revokes, implements) arrive with the regulation "
        "layer's provider."
    ),
    input_schema=_schema({"ref": REF, **load_schema()["$defs"]["links_request"]["properties"]}, ["ref"]),
    output_schema=shape_schema("link_page"),
)


def _search(kinds: list[str]) -> ToolSpec:
    return ToolSpec(
        name=SEARCH,
        version=VERSION,
        description=(
            f"Searches the passages of {_plural(kinds)} for what speaks to a question, in Indonesian or English. Use "
            "it to find what an issuer wrote about a topic, then read a hit for its context. Filters are explicit "
            "and never relaxed for you: kinds, issuers, documents (search within these whole documents, e.g. those "
            "industry_context named), published_from and published_to, in_force_on, legal_force. Returns hits, best "
            "first, each with its rank, a score comparable only within one call, and matched_by. An empty page says "
            "why: no_match (rephrase) or filters_exclude_all (widen the filters)."
        ),
        input_schema=shape_schema("search_request"),
        output_schema=shape_schema("hit_page"),
    )


def _plural(kinds: list[str]) -> str:
    named = [f"{kind}s" for kind in kinds]
    return named[0] if len(named) == 1 else f"{', '.join(named[:-1])} and {named[-1]}"
