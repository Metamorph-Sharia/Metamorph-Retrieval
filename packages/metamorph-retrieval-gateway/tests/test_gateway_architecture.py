"""The gateway's rules (retrieval-architecture.md §9): its application knows only the contract; only its adapters
know MCP, HTTP and OpenTelemetry; its client knows only the contract and HTTP; and no part of it imports a provider,
which the wiring names instead."""

import ast
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "metamorph_retrieval_gateway"
OWN = "metamorph_retrieval_gateway"
CONTRACT = "metamorph_retrieval_contract"
ADAPTERS = {CONTRACT, f"{OWN}.application", f"{OWN}.adapters", "mcp", "mcp_types", "starlette", "anyio",
            "opentelemetry"}
PROVIDERS = ("metamorph_market_retrieval", "metamorph_regulation_standin")


def imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def outside(paths: list[Path], allowed: set[str]) -> set[str]:
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    return {
        f"{path.relative_to(PACKAGE)}: {module}"
        for path in paths
        for module in imports(path)
        if module.split(".")[0] not in stdlib
        and not any(module == name or module.startswith(f"{name}.") for name in allowed)
    }


def test_the_application_knows_only_the_contract() -> None:
    assert outside(list((PACKAGE / "application").rglob("*.py")), {CONTRACT, f"{OWN}.application"}) == set()


def test_only_the_adapters_know_mcp_http_and_opentelemetry() -> None:
    assert outside(list((PACKAGE / "adapters").rglob("*.py")), ADAPTERS) == set()


def test_the_client_knows_only_the_contract_and_http() -> None:
    assert outside([PACKAGE / "client.py"], {CONTRACT, "httpx"}) == set()


def test_no_part_of_the_gateway_imports_a_provider() -> None:
    assert {f"{path.relative_to(PACKAGE)}: {module}" for path in PACKAGE.rglob("*.py") for module in imports(path)
            if module.startswith(PROVIDERS)} == set()
