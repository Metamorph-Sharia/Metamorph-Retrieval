"""Every provider, the gateway and the agent's client depend on this package, so what it imports is a short list."""

import ast
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "metamorph_retrieval_contract"
THIRD_PARTY = {"jsonschema"}  # applies the JSON Schema, which is the formal contract


def imported_modules(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_the_contract_imports_only_the_standard_library_jsonschema_and_itself() -> None:
    allowed = set(sys.stdlib_module_names) | THIRD_PARTY | {"metamorph_retrieval_contract", "__future__"}
    outside = {
        f"{path.name}: {module}"
        for path in PACKAGE.rglob("*.py")
        for module in imported_modules(path)
        if module not in allowed
    }
    assert outside == set()


def test_the_schema_is_a_valid_json_schema_with_every_shape_the_codec_reads() -> None:
    from jsonschema import Draft202012Validator

    from metamorph_retrieval_contract.schema import load_schema

    schema = load_schema()
    Draft202012Validator.check_schema(schema)
    assert {"evidence", "hit_page", "link_page", "search_request", "links_request", "manifest", "error"} <= set(
        schema["$defs"]
    )
