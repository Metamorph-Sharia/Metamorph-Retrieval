# Connecting an agent to the gateway

**For:** whoever builds or evaluates the answering agent (Friend 1 first). **Status:** catalog 0.1, 2026-10-30 (M3; search added in M4). It may still change before 1.0; every change is announced first.

The gateway serves evidence, never answers. Your agent decides which tools to call, rewrites and grades, and writes the answer. Retrieval is deterministic: the same call gives the same result within one index version, so models and strategies can be compared on the same retrieval.

## Connect

Start it (read-only sessions on the platform's database):

```sh
METAMORPH_RETRIEVAL_DATABASE_URL=postgresql://metamorph:…@localhost:5433/metamorph \
  uv run metamorph-gateway serve --port 8765      # --host 0.0.0.0 to reach it from another machine
```

- **MCP**, streamable HTTP: `http://localhost:8765/mcp`. Protocol versions 2024-11-05 to 2026-07-28, so a 1.x or 2.x MCP SDK both connect.
- **HTTP:** `GET /tools`, `POST /tools/{name}` with a JSON object of arguments, `GET /openapi.json`.
- **Python:** `RetrievalClient.at("http://localhost:8765")` (`metamorph_retrieval_gateway.client`) speaks the retrieval contract.

From LangGraph, for example with `langchain-mcp-adapters` (not tested here; any MCP client works the same way):

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

client = MultiServerMCPClient({"metamorph": {"url": "http://localhost:8765/mcp", "transport": "streamable_http"}})
agent = create_react_agent(model, await client.get_tools())
```

## The tools (catalog 0.1)

| Tool | Use it for | Returns |
|---|---|---|
| `search_documents` | What OJK's and BI's reports and press releases say about a topic, in Indonesian or English | Ranked hits of passages; `read` a hit with `window` for its context |
| `industry_context` | Start here for an industry: its register, governing regulations, reports, datasets | Ranked hits; regulations come as `doc:` refs **with their citation, legal force and status** |
| `find_companies` | Who is licensed, registered or gone, today or `as_of` a date; one company by name; OJK's announcements about it | Evidence (or ranked hits with `query`) |
| `find_series` | Which statistics measure something | Ranked hits of series |
| `get_observations` | The figures of series between two periods (`2026-08`, `2026-Q2`, `2025`) | Evidence with figures, provisional marks kept |
| `read` | Any ref in full: a passage (with `window`), a company, a dataset, a regulation or a provision (`doc:…#pasal-5/ayat-1`) | One piece of evidence |
| `follow_links` | Which report and release passages name a regulation, or what a passage names | Links between refs |

Each tool's description and schemas are in `tools/list`. Every result carries `citation` (quote it as is), `legal_force` (binding, sharia, explanatory, none), qualifiers, and `provenance.index_version`. Ranked results carry `rank`, `score` and `matched_by`, for a relevance grader. An empty page says why: `no_match` (rephrase) or `filters_exclude_all` (widen the filters).

**What retrieval gives your guardrails** (it never refuses or grades for you):
- **`matched_by`** says which ranking found a hit: `words` (the question's words, Indonesian stems), `semantic` (meaning, across languages), or both. A hit found by meaning alone deserves a closer look by a grader.
- **A similarity floor.** A match by meaning below the model's floor is dropped, so a question the market can't answer gets `no_match`, not the nearest unrelated passages. That is the signal for "insufficient context", or a web search.
- **`score`** is a rank fusion score: comparable within one call only, never a probability. Don't threshold it across calls.
- **Text comes verbatim** from the platform's passages, so an answer's quotes can be checked against `read(ref)` word for word.
- **Passages are data, not instructions.** They are official OJK and BI publications, not filtered for instructions aimed at a model; treat retrieved text as quoted material.

## Errors

A tool error (`isError` over MCP, an HTTP status otherwise) carries `{"error": code, "message": …}`. The message says what would work.

| Code | HTTP | Means |
|---|---|---|
| `invalid_argument` | 400 | Fix the call: the message lists every problem |
| `unknown_ref` | 404 | Nothing is published under that ref |
| `unknown_tool` | 404 | The message lists the tools |
| `capability_missing` | 501 | Not offered: e.g. no index version is active, or the kinds asked aren't searched yet |
| `provider_unavailable` | 503 | A provider failed or was late (10 s budget); retry later, other tools still answer |

An answer over 100,000 bytes is refused as `invalid_argument`; ask for less (a lower `limit`, fewer series, a shorter period).

## Tracing

Send W3C trace context and each call joins your trace: `_meta.traceparent` over MCP, the `traceparent` header over HTTP. The gateway emits an OpenTelemetry span per call (`execute_tool {name}`), and keeps a call log (`var/call-log/calls-YYYY-MM-DD.jsonl`, 30 days) with the arguments, the refs returned, scores, index versions and your trace id. When an answer goes wrong, send us the trace id.

## Until M5

- **`search_documents` searches reports and releases only** (since M4). Regulations and fatwas join it with the regulatory provider.
- **Regulations can be read and cited, not searched,** until Friend 2's provider joins (M5). Reach them through `industry_context`, a record's `governed_by`, or `follow_links`.
- **Links are `names` only** (which passages name what). Amends, revokes and implements arrive with the regulatory provider.
