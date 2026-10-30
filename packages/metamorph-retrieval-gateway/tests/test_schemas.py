import json

from memory_provider import MemoryProvider
from retrieval_samples import company, report_passage

from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.evidence import Page
from metamorph_retrieval_contract.schema import json_problems, shape_schema
from metamorph_retrieval_gateway.adapters.schemas import inlined


def test_a_schema_is_inlined_into_one_object_schema_with_no_refs() -> None:
    schema = inlined(shape_schema("evidence_page"))

    assert schema["type"] == "object"
    assert "$ref" not in json.dumps(schema) and "$defs" not in schema


def test_an_inlined_schema_accepts_and_refuses_as_the_original_does() -> None:
    schema = inlined(shape_schema("evidence_page"))
    page = codec.to_dict(Page((report_passage(), company())))

    assert json_problems(page, schema) == []
    assert json_problems(page | {"items": [{"ref": "not a ref"}]}, schema) != []


def test_a_schema_without_a_root_type_is_given_object() -> None:
    either = {"anyOf": [shape_schema("hit_page"), shape_schema("evidence_page")]}

    assert inlined(either)["type"] == "object"


def test_every_memory_tool_schema_inlines() -> None:
    for tool in MemoryProvider().manifest().tools:
        assert inlined(tool.input_schema)["type"] == "object"
