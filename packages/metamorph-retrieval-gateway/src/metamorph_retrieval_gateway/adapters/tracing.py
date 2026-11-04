"""Calls as OpenTelemetry spans: a call, named and attributed by the GenAI conventions (`execute_tool {tool}`), holding
a span for each of its stages. Langfuse reads its fields from the `langfuse.observation.*` attributes; any other
backend keeps them as plain attributes.

A span's parent is the span already current (the MCP server's own, which read the agent's `_meta`), or else the
agent's trace context from the request. With no tracer provider configured, spans cost nothing; adapters/trace_export.py
sends them out.

A question stays in the call log and out of the trace unless the deployment asks for it, as mira-ai-chatbot's traces
do: with content "metadata", any text holding a space is replaced. What came back is refs and scores, always sent.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime

from opentelemetry import context, trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, Status, StatusCode, TraceFlags, Tracer

from metamorph_retrieval_gateway.application.calls import Call, TraceContext
from metamorph_retrieval_gateway.application.catalog import SEARCH

TRACEPARENT = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})")
NANOSECONDS = 1_000_000_000
CONTENT = ("metadata", "full")
REDACTED = "[redacted]"
IDENTIFIER = re.compile(r"\S{1,200}")


def trace_from(traceparent: str | None) -> TraceContext | None:
    """The W3C `traceparent` header's context, or None when there is none or it isn't one."""
    match = TRACEPARENT.fullmatch(traceparent.strip()) if traceparent else None
    if not match or set(match[1]) == {"0"} or set(match[2]) == {"0"}:
        return None
    return TraceContext(match[1], match[2], sampled=bool(int(match[3], 16) & 1))


class SpanCallLog:
    def __init__(self, tracer: Tracer | None = None, *, content: str = "metadata") -> None:
        self.tracer = tracer or trace.get_tracer("metamorph_retrieval_gateway")
        self.content = content

    def record(self, call: Call) -> None:
        span = self.tracer.start_span(f"execute_tool {call.tool}", context=_parent(call.trace),
                                      start_time=_nanoseconds(call.started_at),
                                      attributes=_attributes(call, self.content))
        for stage in call.stages:
            inside = trace.set_span_in_context(span)
            self.tracer.start_span(stage.name, context=inside, start_time=_nanoseconds(stage.started_at),
                                   attributes={"langfuse.observation.type": "span"}
                                   ).end(end_time=_ended(stage.started_at, stage.duration_ms))
        if call.error:
            span.set_status(Status(StatusCode.ERROR, call.message))
        span.end(end_time=_ended(call.started_at, call.duration_ms))


def _nanoseconds(moment: datetime) -> int:
    return int(moment.timestamp() * NANOSECONDS)


def _ended(started_at: datetime, duration_ms: float) -> int:
    return _nanoseconds(started_at) + round(duration_ms * NANOSECONDS / 1000)


def _parent(agent: TraceContext | None) -> context.Context | None:
    if trace.get_current_span().get_span_context().is_valid or agent is None:
        return None  # the current context
    remote = SpanContext(trace_id=int(agent.trace_id, 16), span_id=int(agent.span_id, 16), is_remote=True,
                         trace_flags=TraceFlags(TraceFlags.SAMPLED if agent.sampled else TraceFlags.DEFAULT))
    return trace.set_span_in_context(NonRecordingSpan(remote))


def _attributes(call: Call, content: str) -> dict[str, object]:
    arguments = call.arguments if content == "full" else _redacted(call.arguments)
    attributes: dict[str, object] = {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": call.tool,
        "langfuse.observation.type": "retriever" if call.tool == SEARCH else "tool",
        "langfuse.observation.input": json.dumps(arguments, ensure_ascii=False),
        "langfuse.observation.output": json.dumps({"items": _items(call)}, ensure_ascii=False),
    }
    if call.warnings and not call.error:
        attributes["langfuse.observation.level"] = "WARNING"
        attributes["langfuse.observation.status_message"] = "; ".join(call.warnings)
    if call.error:
        attributes["error.type"] = call.error
    metadata = {
        "call_id": call.id,
        "result_count": len(call.refs),
        "top_score": max(call.scores, default=None),
        "index_versions": call.index_versions,
        "empty_reason": call.empty_reason,
        "warnings": call.warnings,
    }
    attributes |= {f"langfuse.observation.metadata.{key}": value for key, value in metadata.items()
                   if value not in (None, ())}
    return attributes


def _items(call: Call) -> list[dict[str, object]]:
    if len(call.scores) == len(call.refs):
        return [{"ref": ref, "score": score} for ref, score in zip(call.refs, call.scores, strict=True)]
    return [{"ref": ref} for ref in call.refs]


def _redacted(value: object) -> object:
    """Identifiers, numbers and booleans kept; text and anything opaque replaced."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value if IDENTIFIER.fullmatch(value) else REDACTED
    if isinstance(value, Mapping):
        return {key: _redacted(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_redacted(item) for item in value]
    return REDACTED
