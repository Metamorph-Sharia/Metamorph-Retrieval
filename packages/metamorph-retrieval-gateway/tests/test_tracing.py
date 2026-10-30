from datetime import UTC, datetime

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from metamorph_retrieval_gateway.adapters.tracing import SpanCallLog, trace_from
from metamorph_retrieval_gateway.application.calls import Call, TraceContext

AGENT = TraceContext("4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7")


@pytest.fixture
def spans() -> InMemorySpanExporter:
    return InMemorySpanExporter()


def log(spans: InMemorySpanExporter) -> SpanCallLog:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(spans))
    return SpanCallLog(provider.get_tracer("test"))


def call(**fields: object) -> Call:
    return Call(**{"id": "c1", "tool": "find_series", "arguments": {}, "trace": AGENT,
                   "started_at": datetime(2026, 10, 30, 9, 1, tzinfo=UTC), "duration_ms": 12.5,
                   "refs": ("series:a", "series:b"), "scores": (0.9, 0.4),
                   "index_versions": ("published-market-sql",)} | fields)  # type: ignore[arg-type]


def test_a_call_is_a_span_in_the_agents_trace_timed_as_it_ran(spans: InMemorySpanExporter) -> None:
    log(spans).record(call())

    (span,) = spans.get_finished_spans()
    assert span.name == "execute_tool find_series"
    assert (format(span.context.trace_id, "032x"), format(span.parent.span_id, "016x")) == (AGENT.trace_id,
                                                                                             AGENT.span_id)
    assert (span.end_time - span.start_time) == 12_500_000
    assert dict(span.attributes) == {
        "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "find_series", "retrieval.call_id": "c1",
        "retrieval.result_count": 2, "retrieval.top_score": 0.9, "retrieval.index_versions": ("published-market-sql",)}


def test_a_failed_call_is_an_error_span_with_its_code(spans: InMemorySpanExporter) -> None:
    log(spans).record(call(refs=(), scores=(), error="provider_unavailable", message="market didn't answer"))

    (span,) = spans.get_finished_spans()
    assert (span.status.status_code, span.status.description) == (StatusCode.ERROR, "market didn't answer")
    assert span.attributes["error.type"] == "provider_unavailable"


def test_an_empty_answer_says_why(spans: InMemorySpanExporter) -> None:
    log(spans).record(call(refs=(), scores=(), empty_reason="no_match"))

    assert spans.get_finished_spans()[0].attributes["retrieval.empty_reason"] == "no_match"


@pytest.mark.parametrize(
    ("header", "context"),
    [
        ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01", AGENT),
        ("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00",
         TraceContext(AGENT.trace_id, AGENT.span_id, sampled=False)),
        ("00-00000000000000000000000000000000-00f067aa0ba902b7-01", None),
        ("not a traceparent", None),
        (None, None),
    ],
)
def test_a_traceparent_is_read_or_ignored(header: str | None, context: TraceContext | None) -> None:
    assert trace_from(header) == context
