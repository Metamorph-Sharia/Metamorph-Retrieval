"""Calls as OpenTelemetry spans, named and attributed by the GenAI conventions (`execute_tool {tool}`).

A span's parent is the span already current (the MCP server's own, which read the agent's `_meta`), or else the
agent's trace context from the request. With no OpenTelemetry SDK configured, spans cost nothing; a deployment
exports them by configuring one (OTEL_* variables, or its own code).
"""

from __future__ import annotations

import re

from opentelemetry import context, trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, Status, StatusCode, TraceFlags, Tracer

from metamorph_retrieval_gateway.application.calls import Call, TraceContext

TRACEPARENT = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})")
NANOSECONDS = 1_000_000_000


def trace_from(traceparent: str | None) -> TraceContext | None:
    """The W3C `traceparent` header's context, or None when there is none or it isn't one."""
    match = TRACEPARENT.fullmatch(traceparent.strip()) if traceparent else None
    if not match or set(match[1]) == {"0"} or set(match[2]) == {"0"}:
        return None
    return TraceContext(match[1], match[2], sampled=bool(int(match[3], 16) & 1))


class SpanCallLog:
    def __init__(self, tracer: Tracer | None = None) -> None:
        self.tracer = tracer or trace.get_tracer("metamorph_retrieval_gateway")

    def record(self, call: Call) -> None:
        start = int(call.started_at.timestamp() * NANOSECONDS)
        end = start + round(call.duration_ms * NANOSECONDS / 1000)
        span = self.tracer.start_span(f"execute_tool {call.tool}", context=_parent(call.trace), start_time=start,
                                      attributes=_attributes(call))
        if call.error:
            span.set_status(Status(StatusCode.ERROR, call.message))
        span.end(end_time=end)


def _parent(agent: TraceContext | None) -> context.Context | None:
    if trace.get_current_span().get_span_context().is_valid or agent is None:
        return None  # the current context
    remote = SpanContext(trace_id=int(agent.trace_id, 16), span_id=int(agent.span_id, 16), is_remote=True,
                         trace_flags=TraceFlags(TraceFlags.SAMPLED if agent.sampled else TraceFlags.DEFAULT))
    return trace.set_span_in_context(NonRecordingSpan(remote))


def _attributes(call: Call) -> dict[str, object]:
    attributes: dict[str, object] = {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": call.tool,
        "retrieval.call_id": call.id,
        "retrieval.result_count": len(call.refs),
    }
    if call.scores:
        attributes["retrieval.top_score"] = max(call.scores)
    if call.index_versions:
        attributes["retrieval.index_versions"] = call.index_versions
    if call.empty_reason:
        attributes["retrieval.empty_reason"] = call.empty_reason
    if call.error:
        attributes["error.type"] = call.error
    return attributes
