"""Tool schemas as agents' clients take them best: one object schema, every `$ref` inlined.

MCP before 2026-07-28 expects `type: object` at a tool schema's root, and some clients turn a schema into a model
without resolving `$ref`. The catalog keeps the contract's shapes as they are; only what is served is inlined.
"""

from __future__ import annotations

from typing import Any

from metamorph_retrieval_contract.provider import JSON

DEFS = "#/$defs/"


def inlined(schema: JSON) -> JSON:
    whole = _resolve(schema, {}, ())
    return whole if "type" in whole else {"type": "object", **whole}


def _resolve(node: Any, defs: JSON, within: tuple[str, ...]) -> Any:
    if isinstance(node, list):
        return [_resolve(item, defs, within) for item in node]
    if not isinstance(node, dict):
        return node
    if "$defs" in node:  # a schema within a schema (anyOf two shapes) brings its own
        defs = {**defs, **node["$defs"]}
        node = {key: value for key, value in node.items() if key not in ("$defs", "$schema")}
    if isinstance(node.get("$ref"), str) and node["$ref"].startswith(DEFS):
        name = node["$ref"].removeprefix(DEFS)
        if name in within:
            raise ValueError(f"$defs/{name} refers to itself; it can't be inlined")
        siblings = {key: value for key, value in node.items() if key != "$ref"}
        return {**_resolve(defs[name], defs, (*within, name)), **_resolve(siblings, defs, within)}
    return {key: _resolve(value, defs, within) for key, value in node.items()}
