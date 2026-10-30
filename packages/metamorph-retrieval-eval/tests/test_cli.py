import json
from pathlib import Path

import pytest
from test_cases import line

from metamorph_retrieval_eval.cli import main


@pytest.fixture
def cases_file(tmp_path: Path) -> Path:
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join([
        "# two cases",
        line(id="series-m2", phase="macro", tool="find_series", arguments={"query": "uang beredar"},
             expect={"refs": ["series:bi:seki:tabel1_1:monthly:row=1"]}),
        line(id="read-unknown", tool="read", arguments={"ref": "report:ojk:lpksi:1999#p-1"},
             expect={"error": "unknown_ref"}),
    ]), encoding="utf-8")
    return path


def test_check_counts_the_cases_by_tool_and_phase(cases_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", str(cases_file)]) == 0
    assert capsys.readouterr().out == (
        f"{cases_file}: 2 cases\n  by tool: find_series 1, read 1\n  by phase: macro 1, industry 1\n"
    )


def test_check_lists_every_problem_and_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(line(phase="retail"), encoding="utf-8")

    assert main(["check", str(path)]) == 1
    assert "line 1: phase: 'retail' is not one of" in capsys.readouterr().out


def test_run_writes_the_report_in_markdown_and_json(cases_file: Path, tmp_path: Path) -> None:
    markdown, data = tmp_path / "report.md", tmp_path / "report.json"

    code = main(["run", str(cases_file), "--provider", "market_like:MarketLike", "--title", "Market",
                 "--markdown", str(markdown), "--json", str(data)])

    assert code == 0
    assert markdown.read_text(encoding="utf-8").startswith("# Market\n")
    assert json.loads(data.read_text(encoding="utf-8"))["overall"]["passed"] == 2


def test_a_provider_that_cant_be_built_is_named(cases_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", str(cases_file), "--provider", "nowhere:Provider"]) == 2
    assert "--provider nowhere:Provider: No module named 'nowhere'" in capsys.readouterr().err
