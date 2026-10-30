import json
from datetime import UTC, datetime

from metamorph_retrieval_gateway.adapters.call_log import JsonLinesCallLog
from metamorph_retrieval_gateway.application.calls import Call, TraceContext


def call(on: datetime, **fields: object) -> Call:
    return Call(**{"id": "c1", "tool": "find_series", "arguments": {"query": "uang beredar"},
                   "trace": TraceContext("4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7"), "started_at": on,
                   "duration_ms": 12.5, "refs": ("series:bi:seki:tabel1_1:monthly:row=1",), "scores": (1.0,),
                   "index_versions": ("published-market-sql",)} | fields)  # type: ignore[arg-type]


def test_each_call_is_one_json_line_in_its_days_file(tmp_path) -> None:  # noqa: ANN001
    log = JsonLinesCallLog(tmp_path)

    log.record(call(datetime(2026, 10, 30, 9, 1, tzinfo=UTC)))
    log.record(call(datetime(2026, 10, 30, 9, 2, tzinfo=UTC), id="c2", error="unknown_ref", message="no such ref"))

    lines = (tmp_path / "calls-2026-10-30.jsonl").read_text(encoding="utf-8").splitlines()
    first, second = (json.loads(line) for line in lines)
    assert first == {
        "id": "c1", "tool": "find_series", "arguments": {"query": "uang beredar"},
        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736", "span_id": "00f067aa0ba902b7",
        "started_at": "2026-10-30T09:01:00+00:00", "duration_ms": 12.5,
        "refs": ["series:bi:seki:tabel1_1:monthly:row=1"], "scores": [1.0], "index_versions": ["published-market-sql"],
        "empty_reason": None, "warnings": [], "error": None, "message": None,
    }
    assert (second["error"], second["message"]) == ("unknown_ref", "no such ref")


def test_a_new_days_file_drops_the_files_older_than_the_retention(tmp_path) -> None:  # noqa: ANN001
    for day in ("2026-09-29", "2026-09-30", "2026-10-01"):
        (tmp_path / f"calls-{day}.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a call log", encoding="utf-8")

    JsonLinesCallLog(tmp_path, retention_days=30).record(call(datetime(2026, 10, 30, tzinfo=UTC)))

    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "calls-2026-09-30.jsonl", "calls-2026-10-01.jsonl", "calls-2026-10-30.jsonl", "notes.txt"]
