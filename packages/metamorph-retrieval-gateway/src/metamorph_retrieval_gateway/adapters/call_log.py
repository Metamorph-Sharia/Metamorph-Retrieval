"""The call log as JSON Lines: one file a day, `calls-YYYY-MM-DD.jsonl`, kept for a retention period.

Files and not a table, for now: the gateway reads the platform's database through read-only sessions, and a table of
its own would need a writing role and a migration in the platform. The lines are the table's rows, so loading them
later is a COPY.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from metamorph_retrieval_gateway.application.calls import Call

RETENTION_DAYS = 30
DAILY = re.compile(r"calls-(\d{4}-\d{2}-\d{2})\.jsonl")


class JsonLinesCallLog:
    def __init__(self, directory: Path, *, retention_days: int = RETENTION_DAYS) -> None:
        self.directory = directory
        self.retention = timedelta(days=retention_days)
        self.lock = threading.Lock()

    def record(self, call: Call) -> None:
        day = call.started_at.date()
        path = self.directory / f"calls-{day.isoformat()}.jsonl"
        with self.lock:
            if not path.exists():
                self.directory.mkdir(parents=True, exist_ok=True)
                self._drop_before(day - self.retention)
            with path.open("a", encoding="utf-8") as lines:
                lines.write(json.dumps(_line(call), ensure_ascii=False) + "\n")

    def _drop_before(self, oldest: date) -> None:
        for path in self.directory.iterdir():
            match = DAILY.fullmatch(path.name)
            if match and date.fromisoformat(match[1]) < oldest:
                path.unlink()


def _line(call: Call) -> dict[str, object]:
    line = asdict(call)
    trace = line.pop("trace")
    return {
        "id": line.pop("id"), "tool": line.pop("tool"), "arguments": line.pop("arguments"),
        "trace_id": trace["trace_id"] if trace else None, "span_id": trace["span_id"] if trace else None,
        "started_at": line.pop("started_at").isoformat(),
        **{key: list(value) if isinstance(value, tuple) else value for key, value in line.items()},
    }
