"""The evaluation judges any provider through the contract alone, and its rings point inward: the cases and their
judging know nothing of running, reporting or the command line."""

import ast
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "metamorph_retrieval_eval"
INNER = {"cases", "scoring"}  # what a case is and how it is judged
OUTER = {"runner", "report", "cli"}  # calling a provider, summing up, the command line


def imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_the_evaluation_imports_only_the_standard_library_the_contract_and_itself() -> None:
    allowed = set(sys.stdlib_module_names) | {"metamorph_retrieval_contract", "metamorph_retrieval_eval", "__future__"}
    outside = {
        f"{path.name}: {module}"
        for path in PACKAGE.rglob("*.py")
        for module in imports(path)
        if module.split(".")[0] not in allowed
    }
    assert outside == set()


def test_the_cases_and_their_judging_never_import_running_or_reporting() -> None:
    inward = {
        f"{path.stem}: {module}"
        for path in PACKAGE.glob("*.py")
        if path.stem in INNER
        for module in imports(path)
        if module.startswith("metamorph_retrieval_eval.") and module.rsplit(".", 1)[1] in OUTER
    }
    assert inward == set()
