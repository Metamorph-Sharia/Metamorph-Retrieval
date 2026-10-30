"""The JSON Schema in `schemas/` is the formal contract; this module applies it, one shape (one $def) at a time."""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

SCHEMA = "retrieval.schema.json"


@cache
def load_schema() -> dict[str, Any]:
    return json.loads(files("metamorph_retrieval_contract").joinpath("schemas", SCHEMA).read_text(encoding="utf-8"))


def shape_schema(shape: str) -> dict[str, Any]:
    """One shape as a schema of its own, e.g. for a tool's input in the agent's catalog."""
    schema = load_schema()
    if shape not in schema["$defs"]:
        raise KeyError(f"no shape {shape!r} in {SCHEMA}")
    return {"$schema": schema["$schema"], "$ref": f"#/$defs/{shape}", "$defs": schema["$defs"]}


def schema_problems(data: Any, shape: str) -> list[str]:
    """Every way `data` breaks the shape, as "path: message", in field order."""
    return _problems(_validator(shape), data)


def json_problems(data: Any, schema: dict[str, Any]) -> list[str]:
    """The same, against any schema: a provider's tool's own input or output schema."""
    return _problems(_checking(schema), data)


@cache
def _validator(shape: str) -> Draft202012Validator:
    schema = shape_schema(shape)
    Draft202012Validator.check_schema(schema)
    return _checking(schema)


def _checking(schema: dict[str, Any]) -> Draft202012Validator:
    # The format checker makes "date" and "date-time" binding, not just documentation.
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _problems(validator: Draft202012Validator, data: Any) -> list[str]:
    errors = sorted(validator.iter_errors(data), key=lambda error: [str(p) for p in error.absolute_path])
    return [f"{_path(error)}: {error.message}" for error in errors]


def _path(error: ValidationError) -> str:
    parts = [f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path]
    return "".join(parts).lstrip(".") or "(value)"
