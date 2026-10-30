"""What the gateway keeps of each call: enough to tell, when an answer goes wrong, whether the evidence was missing,
not retrieved, or ranked too low, and to turn a bad answer into a new evaluation case.

A call log is a port: the adapters write it as JSON Lines and as OpenTelemetry spans. The agent's trace context
comes in on the request (MCP `_meta`, HTTP `traceparent`); the interface sets TRACE, so one question is one trace
across the agent and retrieval.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from metamorph_retrieval_contract.provider import JSON


@dataclass(frozen=True)
class TraceContext:
    """W3C trace context: the agent's trace, and its span that made the call."""

    trace_id: str  # 32 hex digits
    span_id: str  # 16 hex digits
    sampled: bool = True


logger = logging.getLogger(__name__)

TRACE: ContextVar[TraceContext | None] = ContextVar("trace", default=None)


@dataclass(frozen=True)
class Call:
    id: str
    tool: str
    arguments: JSON
    trace: TraceContext | None
    started_at: datetime
    duration_ms: float
    refs: tuple[str, ...] = ()  # what came back, in order
    scores: tuple[float, ...] = ()  # a ranked tool's, in the same order
    index_versions: tuple[str, ...] = ()  # the builds that answered
    empty_reason: str | None = None
    warnings: tuple[str, ...] = ()
    error: str | None = None  # the error's code, when it failed
    message: str | None = None  # and its message


class CallLog(Protocol):
    def record(self, call: Call) -> None: ...


class NoCallLog:
    def record(self, call: Call) -> None:
        pass


class AllCallLogs:
    """Each call to every log; one that fails costs only its own record."""

    def __init__(self, logs: Sequence[CallLog]) -> None:
        self.logs = tuple(logs)

    def record(self, call: Call) -> None:
        for log in self.logs:
            try:
                log.record(call)
            except Exception:  # noqa: BLE001
                logger.exception("call %s not recorded by %s", call.id, type(log).__name__)
