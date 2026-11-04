"""Spans leave the gateway over OTLP only when an endpoint is set, with the headers the environment gives."""

import os
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import pytest

from metamorph_retrieval_gateway.adapters.trace_export import export_spans


class Collector(BaseHTTPRequestHandler):
    received: list[tuple[str, str | None, int]] = []

    def do_POST(self) -> None:  # noqa: N802 - http.server's name
        length = int(self.headers["Content-Length"])
        self.rfile.read(length)
        self.received.append((self.path, self.headers["Authorization"], length))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture
def collector() -> str:
    Collector.received = []
    server = HTTPServer(("127.0.0.1", 0), Collector)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_without_an_endpoint_nothing_is_exported() -> None:
    assert export_spans({}) is None


def test_with_an_endpoint_spans_are_sent_with_its_headers(collector: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"{collector}/api/public/otel")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=Basic%20abc")

    provider = export_spans({"OTEL_EXPORTER_OTLP_ENDPOINT": f"{collector}/api/public/otel"})
    provider.get_tracer("test").start_span("a call").end()
    provider.shutdown()

    ((path, authorization, length),) = Collector.received
    assert (path, authorization) == ("/api/public/otel/v1/traces", "Basic abc")
    assert length > 0


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_a_stopped_server_sends_the_spans_it_still_holds(collector: str, tmp_path: Path) -> None:
    port = free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "metamorph_retrieval_gateway.cli", "serve", "--port", str(port)],
        env=os.environ | {"PYTHONPATH": os.pathsep.join(sys.path), "OTEL_EXPORTER_OTLP_ENDPOINT": collector,
                          "METAMORPH_RETRIEVAL_PROVIDERS": "fakes:regulations",
                          "METAMORPH_RETRIEVAL_CALL_LOG": str(tmp_path)})
    try:
        for _ in range(100):
            try:
                httpx.get(f"http://127.0.0.1:{port}/health")
                break
            except httpx.TransportError:
                time.sleep(0.1)
        answer = httpx.post(f"http://127.0.0.1:{port}/tools/read", json={"ref": "doc:ojk:pojk:2024:40"})
        assert answer.status_code == 200

        server.send_signal(signal.SIGTERM)  # at once: the batch waits five seconds to be sent
        server.wait(timeout=20)
    finally:
        server.kill()

    assert [path for path, _, _ in Collector.received] == ["/v1/traces"]
