import json
from datetime import UTC, datetime

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from metamorph_retrieval_gateway.adapters.tracing import SpanCallLog, trace_from
from metamorph_retrieval_gateway.application.calls import Call, Stage, TraceContext

AGENT = TraceContext("4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7")


@pytest.fixture
def spans() -> InMemorySpanExporter:
    return InMemorySpanExporter()


def log(spans: InMemorySpanExporter, content: str = "metadata") -> SpanCallLog:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(spans))
    return SpanCallLog(provider.get_tracer("test"), content=content)


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
        "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "find_series",
        "langfuse.observation.type": "tool",
        "langfuse.observation.input": "{}",
        "langfuse.observation.output": json.dumps({"items": [{"ref": "series:a", "score": 0.9},
                                                             {"ref": "series:b", "score": 0.4}]}),
        "langfuse.observation.metadata.call_id": "c1", "langfuse.observation.metadata.result_count": 2,
        "langfuse.observation.metadata.top_score": 0.9,
        "langfuse.observation.metadata.index_versions": ("published-market-sql",)}


def test_a_search_is_a_retriever(spans: InMemorySpanExporter) -> None:
    log(spans).record(call(tool="search_documents"))

    assert spans.get_finished_spans()[0].attributes["langfuse.observation.type"] == "retriever"


def test_a_question_stays_out_of_the_trace_unless_asked_for(spans: InMemorySpanExporter) -> None:
    arguments = {"query": "bolehkah akad qardh berbunga", "kinds": ["regulation"], "in_force_on": "2026-11-04",
                 "limit": 8}
    log(spans).record(call(arguments=arguments))

    assert json.loads(spans.get_finished_spans()[0].attributes["langfuse.observation.input"]) == {
        "query": "[redacted]", "kinds": ["regulation"], "in_force_on": "2026-11-04", "limit": 8}


def test_a_trace_of_full_content_keeps_the_question(spans: InMemorySpanExporter) -> None:
    arguments = {"query": "bolehkah akad qardh berbunga"}
    log(spans, content="full").record(call(arguments=arguments))

    assert json.loads(spans.get_finished_spans()[0].attributes["langfuse.observation.input"]) == arguments


def test_a_degraded_answer_is_a_warning_with_its_reason(spans: InMemorySpanExporter) -> None:
    log(spans).record(call(warnings=("not reranked: the fused order stands",)))

    attributes = spans.get_finished_spans()[0].attributes
    assert attributes["langfuse.observation.level"] == "WARNING"
    assert attributes["langfuse.observation.status_message"] == "not reranked: the fused order stands"
    assert attributes["langfuse.observation.metadata.warnings"] == ("not reranked: the fused order stands",)


def test_each_stage_is_a_span_inside_the_call_timed_as_it_ran(spans: InMemorySpanExporter) -> None:
    stage = Stage("rerank", datetime(2026, 10, 30, 9, 1, 0, 2000, tzinfo=UTC), 7.5)
    log(spans).record(call(stages=(stage,)))

    finished = {span.name: span for span in spans.get_finished_spans()}
    child, parent = finished["rerank"], finished["execute_tool find_series"]
    assert child.parent.span_id == parent.context.span_id
    assert child.context.trace_id == parent.context.trace_id
    assert child.end_time - child.start_time == 7_500_000
    assert abs(child.start_time - parent.start_time - 2_000_000) < 1_000  # a timestamp is a float: within a microsecond
    assert child.attributes["langfuse.observation.type"] == "span"


def test_a_failed_call_is_an_error_span_with_its_code(spans: InMemorySpanExporter) -> None:
    log(spans).record(call(refs=(), scores=(), error="provider_unavailable", message="market didn't answer"))

    (span,) = spans.get_finished_spans()
    assert (span.status.status_code, span.status.description) == (StatusCode.ERROR, "market didn't answer")
    assert span.attributes["error.type"] == "provider_unavailable"


def test_an_empty_answer_says_why(spans: InMemorySpanExporter) -> None:
    log(spans).record(call(refs=(), scores=(), empty_reason="no_match"))

    assert spans.get_finished_spans()[0].attributes["langfuse.observation.metadata.empty_reason"] == "no_match"


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
