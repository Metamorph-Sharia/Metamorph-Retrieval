"""The catalog over MCP, as an agent's MCP client sees it (in process here; over streamable HTTP when served)."""

import json

import pytest
from fakes import POJK_40, Industries, Recorded, Regulations
from mcp import Client
from memory_provider import MemoryProvider
from retrieval_samples import regulation

from metamorph_retrieval_contract import codec
from metamorph_retrieval_gateway.adapters.mcp import mcp_server
from metamorph_retrieval_gateway.application.calls import TraceContext
from metamorph_retrieval_gateway.application.catalog import Catalog
from metamorph_retrieval_gateway.application.gateway import Gateway

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def server(log: Recorded | None = None):  # noqa: ANN201
    return mcp_server(Catalog(Gateway([MemoryProvider(), Regulations(), Industries()]), calls=log))


async def test_an_agent_lists_the_catalogs_tools_with_plain_object_schemas() -> None:
    async with Client(server()) as client:
        tools = (await client.list_tools()).tools

    assert [tool.name for tool in tools] == ["search_documents", "read", "follow_links", "count", "industry_context"]
    for tool in tools:
        assert tool.description
        assert tool.input_schema["type"] == "object" and "$ref" not in json.dumps(tool.input_schema)
        assert tool.output_schema["type"] == "object"


async def test_a_tool_answers_with_structured_content_and_the_same_json_as_text() -> None:
    async with Client(server()) as client:
        result = await client.call_tool("read", {"ref": str(POJK_40)})

    assert not result.is_error
    assert result.structured_content == codec.to_dict(regulation())
    assert json.loads(result.content[0].text) == codec.to_dict(regulation())


async def test_an_error_is_a_tool_error_the_agent_reads_and_can_act_on() -> None:
    async with Client(server()) as client:
        unknown = await client.call_tool("read", {"ref": "doc:ojk:pojk:1999:1"})
        misnamed = await client.call_tool("get_provision", {"ref": str(POJK_40)})

    assert unknown.is_error and json.loads(unknown.content[0].text) == {
        "error": "unknown_ref", "message": "regulation holds nothing under doc:ojk:pojk:1999:1"}
    assert json.loads(misnamed.content[0].text)["error"] == "unknown_tool"


async def test_the_agents_trace_context_reaches_the_call_log() -> None:
    log = Recorded()

    async with Client(server(log)) as client:
        await client.call_tool("count", {"kind": "report"},
                               meta={"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"})

    assert log.calls[0].trace == TraceContext("4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7")
