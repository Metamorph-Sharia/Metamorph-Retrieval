"""`metamorph-gateway`: serve the gateway, or list its catalog.

    METAMORPH_RETRIEVAL_DATABASE_URL=postgresql://metamorph:…@localhost:5433/metamorph \\
        uv run metamorph-gateway serve --port 8765

An agent connects its MCP client to http://localhost:8765/mcp (streamable HTTP); other clients use the HTTP routes.
See wiring.py for the rest of the environment.
"""

from __future__ import annotations

import argparse
import os
import sys

import uvicorn

from metamorph_retrieval_gateway.adapters.http import http_app
from metamorph_retrieval_gateway.wiring import catalog_from

DEFAULT_PORT = 8765


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metamorph-gateway", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="serve MCP at /mcp and the HTTP routes")
    serve.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to serve other machines (default 127.0.0.1)")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    commands.add_parser("tools", help="list the catalog's tools")
    arguments = parser.parse_args(argv)

    catalog = catalog_from(os.environ)
    if arguments.command == "tools":
        for tool in catalog.tools():
            print(f"{tool.name} {tool.version}: {tool.description.split('. ')[0]}.")
        return 0
    uvicorn.run(http_app(catalog, host=arguments.host), host=arguments.host, port=arguments.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
