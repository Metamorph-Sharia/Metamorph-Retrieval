"""The catalog over MCP: one tool for each of the catalog's, with its description and inlined schemas.

A tool's answer is its structured content, and the same JSON as text for clients that read only text. An error is
a tool error (`isError`) whose text is the contract's `{"error", "message"}`, so the agent can read it and correct
its call. The agent's trace context comes in `_meta.traceparent`.
"""

from __future__ import annotations

import json
from typing import Any

import anyio
from mcp.server.lowlevel import Server
from mcp_types import CallToolRequestParams, CallToolResult, ListToolsResult, PaginatedRequestParams, TextContent, Tool

from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.errors import RetrievalError
from metamorph_retrieval_contract.provider import JSON
from metamorph_retrieval_gateway.adapters.schemas import inlined
from metamorph_retrieval_gateway.adapters.tracing import trace_from
from metamorph_retrieval_gateway.application.calls import TRACE
from metamorph_retrieval_gateway.application.catalog import Catalog

NAME = "metamorph-retrieval"
VERSION = "0.1.0"
INSTRUCTIONS = (
    "Evidence about Indonesian Islamic finance: who OJK licenses, market statistics, OJK's and BI's reports and "
    "releases, and the regulations they name. Every tool returns evidence, never an answer. Quote each piece by its "
    "citation, and weigh it by its legal_force: only binding (laws, regulations) and sharia (DSN-MUI) evidence can "
    "require anything; reports, releases, statistics and registers (legal_force none) report or count. Pass refs "
    "from one tool to the next, and read a ref for its full text. Filters are never relaxed for you: an empty page "
    "says why, no_match or filters_exclude_all."
)


def mcp_server(catalog: Catalog) -> Server[Any]:
    tools = [Tool(name=tool.name, description=tool.description, input_schema=inlined(tool.input_schema),
                  output_schema=inlined(tool.output_schema)) for tool in catalog.tools()]

    async def list_tools(context: Any, params: PaginatedRequestParams | None) -> ListToolsResult:
        return ListToolsResult(tools=tools)

    async def call_tool(context: Any, params: CallToolRequestParams) -> CallToolResult:
        trace = trace_from((context.meta or {}).get("traceparent"))

        def run() -> JSON:
            token = TRACE.set(trace)
            try:
                return catalog.run(params.name, params.arguments or {})
            finally:
                TRACE.reset(token)

        try:
            output = await anyio.to_thread.run_sync(run)
        except RetrievalError as error:
            return CallToolResult(content=[_text(codec.to_dict(error))], is_error=True)
        return CallToolResult(content=[_text(output)], structured_content=output)

    return Server(NAME, version=VERSION, instructions=INSTRUCTIONS, on_list_tools=list_tools, on_call_tool=call_tool)


def _text(value: JSON) -> TextContent:
    return TextContent(text=json.dumps(value, ensure_ascii=False))
