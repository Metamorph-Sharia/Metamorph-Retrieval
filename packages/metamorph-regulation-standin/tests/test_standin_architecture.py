"""The stand-in's rings point inward, as the market provider's do: the domain knows only the contract, the use cases
only the domain and their ports, and only the adapters know PostgreSQL. It depends on the contract alone."""

import ast
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "metamorph_regulation_standin"
OWN = "metamorph_regulation_standin"
CONTRACT = "metamorph_retrieval_contract"
ALLOWED = {
    "domain": {CONTRACT, f"{OWN}.domain"},
    "application": {CONTRACT, f"{OWN}.domain", f"{OWN}.application"},
    "adapters": {CONTRACT, f"{OWN}.domain", f"{OWN}.application", f"{OWN}.adapters", "psycopg"},
}


def imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def outside(ring: str) -> set[str]:
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    return {
        f"{path.relative_to(PACKAGE)}: {module}"
        for path in (PACKAGE / ring).rglob("*.py")
        for module in imports(path)
        if module.split(".")[0] not in stdlib and not any(module == allowed or module.startswith(f"{allowed}.")
                                                          for allowed in ALLOWED[ring])
    }


def test_the_domain_knows_only_the_contract() -> None:
    assert outside("domain") == set()


def test_the_use_cases_know_only_the_domain_and_their_ports() -> None:
    assert outside("application") == set()


def test_only_the_adapters_know_postgresql() -> None:
    assert outside("adapters") == set()
