"""The gateway's one web app: MCP at /mcp for agents, and the same catalog over plain HTTP for tests and clients
without MCP.

    GET  /health             is it up
    GET  /manifest           the providers together, as the contract's manifest
    GET  /tools              the catalog: names, descriptions, inlined schemas
    POST /tools/{name}       call a tool with a JSON object of arguments
    POST /describe           {"refs": [...]}: the cards held, in the order asked
    GET  /openapi.json       the same, as OpenAPI 3.1

An error is the contract's `{"error", "message"}` with an HTTP status for its code. The agent's trace context comes
in the `traceparent` header.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import anyio
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.errors import InvalidArgument, RetrievalError
from metamorph_retrieval_contract.provider import JSON, ToolSpec
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_gateway.adapters.mcp import NAME, VERSION, mcp_server
from metamorph_retrieval_gateway.adapters.schemas import inlined
from metamorph_retrieval_gateway.adapters.tracing import trace_from
from metamorph_retrieval_gateway.application.calls import TRACE
from metamorph_retrieval_gateway.application.catalog import Catalog

STATUS = {
    "invalid_argument": 400,
    "unknown_ref": 404,
    "unknown_tool": 404,
    "capability_missing": 501,
    "provider_unavailable": 503,
}
ERROR = {"type": "object", "required": ["error", "message"],
         "properties": {"error": {"enum": list(STATUS)}, "message": {"type": "string"}}}


def http_app(catalog: Catalog, *, host: str = "127.0.0.1") -> Starlette:
    tools = [_served(tool) for tool in catalog.tools()]

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def manifest(request: Request) -> JSONResponse:
        return await _answer(request, lambda: codec.to_dict(catalog.provider.manifest()))

    async def listed(request: Request) -> JSONResponse:
        return JSONResponse(tools)

    async def call_tool(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        return await _answer(request, lambda body: catalog.run(name, body))

    async def describe(request: Request) -> JSONResponse:
        return await _answer(request, lambda body: {"items": [
            codec.to_dict(card) for card in catalog.provider.describe([Ref.parse(ref) for ref in _refs(body)])]})

    async def openapi(request: Request) -> JSONResponse:
        return JSONResponse(_openapi(tools))

    routes = [
        Route("/health", health),
        Route("/manifest", manifest),
        Route("/tools", listed),
        Route("/tools/{name}", call_tool, methods=["POST"]),
        Route("/describe", describe, methods=["POST"]),
        Route("/openapi.json", openapi),
    ]
    return mcp_server(catalog).streamable_http_app(streamable_http_path="/mcp", stateless_http=True,
                                                   json_response=True, host=host, custom_starlette_routes=routes)


async def _answer(request: Request, work: Callable[..., JSON]) -> JSONResponse:
    """The work's answer, done off the event loop under the caller's trace; or its error, with its status."""
    trace = trace_from(request.headers.get("traceparent"))
    try:
        body = await _body(request) if request.method == "POST" else None

        def run() -> JSON:
            token = TRACE.set(trace)
            try:
                return work(body) if body is not None else work()
            finally:
                TRACE.reset(token)

        return JSONResponse(await anyio.to_thread.run_sync(run))
    except RetrievalError as error:
        return JSONResponse(codec.to_dict(error), status_code=STATUS.get(error.code, 500))


async def _body(request: Request) -> dict[str, Any]:
    try:
        body = json.loads(await request.body() or b"{}")
    except json.JSONDecodeError:
        body = None
    if not isinstance(body, dict):
        raise InvalidArgument("the body must be a JSON object")
    return body


def _refs(body: dict[str, Any]) -> list[str]:
    refs = body.get("refs")
    if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
        raise InvalidArgument("refs: a list of refs, such as doc:ojk:pojk:2024:40")
    return refs


def _served(tool: ToolSpec) -> JSON:
    return {"name": tool.name, "version": tool.version, "description": tool.description,
            "input_schema": inlined(tool.input_schema), "output_schema": inlined(tool.output_schema)}


def _openapi(tools: list[JSON]) -> JSON:
    def failing(status: int) -> JSON:
        codes = [code for code, code_status in STATUS.items() if code_status == status]
        return {"description": ", ".join(codes), "content": {"application/json": {"schema": ERROR}}}

    return {
        "openapi": "3.1.0",
        "info": {"title": NAME, "version": VERSION},
        "paths": {
            f"/tools/{tool['name']}": {"post": {
                "operationId": tool["name"],
                "description": tool["description"],
                "requestBody": {"required": True, "content": {"application/json": {"schema": tool["input_schema"]}}},
                "responses": {"200": {"description": "The answer",
                                      "content": {"application/json": {"schema": tool["output_schema"]}}},
                              **{str(status): failing(status) for status in sorted(set(STATUS.values()))}},
            }}
            for tool in tools
        },
    }
