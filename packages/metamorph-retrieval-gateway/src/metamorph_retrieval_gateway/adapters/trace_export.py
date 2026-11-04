"""Sending spans out over OTLP, with OpenTelemetry's own settings, so the gateway names no tracing product.

    OTEL_EXPORTER_OTLP_ENDPOINT   where to send them; with none set, nothing leaves the process
    OTEL_EXPORTER_OTLP_HEADERS    their headers, as key=value pairs, percent-encoded

For Langfuse the endpoint is <its address>/api/public/otel, and the headers Authorization=Basic%20<base64 of
public_key:secret_key>,x-langfuse-ingestion-version=4. Spans go in batches on their own thread: a slow or missing
collector costs a warning in the logs, never an answer. What is left is sent when the process exits.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider

ENDPOINTS = ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
SERVICE = "metamorph-retrieval-gateway"


def export_spans(environment: Mapping[str, str]) -> TracerProvider | None:
    """A tracer provider sending to the environment's endpoint, or None when it names none."""
    if not any(environment.get(name) for name in ENDPOINTS):
        return None
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        raise ValueError("an OTLP endpoint is set: install metamorph-retrieval-gateway[otlp]") from None
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    return provider
