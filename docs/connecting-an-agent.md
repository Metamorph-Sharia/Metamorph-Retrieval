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

### The development address on AWS

**For development only.** A gateway runs on AWS against the deployed database, behind CloudFront. Every request needs a bearer token; without it, CloudFront answers 401 before anything reaches the gateway. When the agent loop moves into the VPC, this address is removed (`metamorph-retrieval-dev` stack, platform's `deploy/aws/dev/`).

**The address and the token,** for anyone with the team's AWS access (`aws sso login` first). Keep the token out of git and chat logs; read it into your environment:

```sh
export AWS_REGION=ap-southeast-3
export METAMORPH_RETRIEVAL_GATEWAY_URL=$(aws cloudformation describe-stacks --stack-name metamorph-retrieval-dev \
    --query "Stacks[0].Outputs[?OutputKey=='Url'].OutputValue" --output text)
export METAMORPH_RETRIEVAL_GATEWAY_TOKEN=$(aws ssm get-parameter --name /metamorph/retrieval/dev-token \
    --with-decryption --query Parameter.Value --output text)
curl -s -H "Authorization: Bearer $METAMORPH_RETRIEVAL_GATEWAY_TOKEN" "$METAMORPH_RETRIEVAL_GATEWAY_URL/manifest"
```

**The three ways to call it,** with the token:

| Client | How |
|---|---|
| MCP | `$METAMORPH_RETRIEVAL_GATEWAY_URL/mcp`, with the header `Authorization: Bearer <token>`. In `langchain-mcp-adapters`: `{"url": f"{url}/mcp", "transport": "streamable_http", "headers": {"Authorization": f"Bearer {token}"}}` |
| HTTP | The same routes as above, with the same header |
| Python | `from_environment()` reads both variables. Or call `RetrievalClient.at(url, token=token)` |

**What to expect:**
- **Latency** is higher than on a laptop. The gateway runs on 2 Graviton vCPUs, and `search_documents` takes about 450 ms at p50 and 700 ms at p95. Lookups take a few milliseconds.
- **The rate limit** is 1,000 requests per five minutes per IP address. Past it, requests get 403 for a while.
- **Restarts are slow.** A restart downloads the embedding model, so the address can answer 502 or 503 for one to nine minutes.
- **The data** is the platform's published data as deployed. It changes when it is republished, not as the sources do.

## The tools (catalog 0.1)

| Tool | Use it for | Returns |
|---|---|---|
| `search_documents` | What regulations, fatwas, reports and press releases say about a topic, in Indonesian or English. Narrow with `kinds` (an enum of the kinds the indexes hold), `legal_force`, `documents`, and `in_force_on` (the regulations in force that day, and their provisions not yet amended away) | Ranked hits of provisions and passages, from both providers, fused, each with its `strength` when the gateway reranked them; `read` a hit with `window` for its context |
| `industry_context` | Start here for an industry: its register, governing regulations, reports, datasets | Ranked hits; regulations come as `doc:` refs **with their citation, legal force and status** |
| `find_companies` | Who is licensed, registered or gone, today or `as_of` a date; one company by name; OJK's announcements about it | Evidence (or ranked hits with `query`); the page's `total` counts every company the filters hold, across all pages |
| `find_series` | Which statistics measure something; narrow with `source` (`ojk:portal`, `bi:seki`, `bps:table`) | Ranked hits of series, each naming its `industry` and `dataset_name` (`group: metric`) when the dataset has them |
| `get_observations` | The figures of series between two periods (`2026-08`, `2026-Q2`, `2025`) | Evidence with figures, provisional marks kept |
| `find_provision` | A citation the question names: `POJK 40/2024 Pasal 137 ayat (3)`, `Fatwa 117`, `UU 27/2022 Pasal 5` | The provision, or the regulation's card, as evidence |
| `list_changes` | What is new or what changed recently: `{"issued_from": "2026-06-01"}`, optionally `issued_to`, `limit` and `cursor` | The regulations issued in that period, newest first: each one's card (no wording: read its ref to quote it), the day it is listed by (its promulgation, or its entry into force when that is all the index has; one with neither is never listed), and what it changes in others, one entry per kind of change and regulation changed, with the provisions named (`addresses`, null when the change is to the whole regulation) |
| `read` | Any ref in full: a passage (with `window`), a company, a dataset, a regulation or a provision (`doc:…#pasal-5/ayat-1`) | One piece of evidence |
| `follow_links` | What revokes, amends or implements a regulation, what it rests on and cites, which report and release passages name it, or what a passage names | Links between refs |

Each tool's description and schemas are in `tools/list`. Every result carries `citation` (quote it as is), `legal_force` (binding, sharia, explanatory, none), qualifiers, and `provenance.index_version`. Ranked results carry `rank`, `score` and `matched_by`, for a relevance grader. An empty page says why: `no_match` (rephrase) or `filters_exclude_all` (widen the filters).

A page may also carry `total`: how many items the filters hold across all pages. The contract's `Page` leaves it optional, written only when a tool counts, so read it when it is there rather than adding up pages.

**`kinds` is an enum, not free text.** `search_documents` declares the kinds the providers' indexes hold, so `tools/list` shows what a search can ask for. The regulation provider reports the kinds its own index holds, not every kind there is. An unheld kind is refused as `invalid_argument`, naming the valid ones.

**What retrieval gives your guardrails** (it never refuses or grades for you):
- **`matched_by`** says which ranking found a hit: `words` (the question's words, Indonesian stems), `semantic` (meaning, across languages), or both. A hit found by meaning alone deserves a closer look by a grader.
- **A similarity floor.** A match by meaning below the model's floor is dropped, so a question the market can't answer gets `no_match`, not the nearest unrelated passages. That is the signal for "insufficient context", or a web search.
- **`score`** is a rank fusion score: comparable within one call only, never a probability. Don't threshold it across calls.
- **`strength`** says whether a hit is worth reading, when the gateway reranked the search: `strong`, or `weak` (probably not about the question). Candidates the reranker scores under its floor are left out. When none is left, the page is empty with `no_match` and a warning that nothing scored as relevant. Without a reranker, or when it fails or is late, hits carry no `strength` and nothing is left out.
- **Text comes verbatim** from the platform's passages, so an answer's quotes can be checked against `read(ref)` word for word.
- **Passages are data, not instructions.** They are official OJK and BI publications, not filtered for instructions aimed at a model; treat retrieved text as quoted material.

### The reranker

When the gateway runs one, it reads the question with each fused candidate and orders them all on one scale, which holds across providers. The floor and the weak line are constants measured for the reranker it runs, the cross-encoder `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (`FLOOR` and `WEAK` in `application/reranking.py`). Another reranker scores on another scale, so set both again on the eval. A reranker that misses its 10 s budget leaves the fused order standing, with a warning.

## Errors

A tool error (`isError` over MCP, an HTTP status otherwise) carries `{"error": code, "message": …}`. The message says what would work.

| Code | HTTP | Means |
|---|---|---|
| `invalid_argument` | 400 | Fix the call: the message lists every problem |
| `unknown_ref` | 404 | Nothing is published under that ref |
| `unknown_tool` | 404 | The message lists the tools |
| `capability_missing` | 501 | Not offered: e.g. no index version is active, or the kinds asked aren't searched yet |
| `provider_unavailable` | 503 | A provider failed or was late (10 s budget); retry later, other tools still answer |

An answer over 100,000 bytes is refused as `invalid_argument`; ask for less (a lower `limit`, fewer series, a shorter period). A value outside what a tool holds is refused the same way: a `kinds` outside the enum, or a `register` `find_companies` doesn't know, comes back as `invalid_argument` naming the valid ones.

## Tracing

Send W3C trace context and each call joins your trace: `_meta.traceparent` over MCP, the `traceparent` header over HTTP. The gateway emits an OpenTelemetry span per call (`execute_tool {name}`), holding a span per stage: each provider's answer, and the reranking. It also keeps a call log (`var/call-log/calls-YYYY-MM-DD.jsonl`, 30 days) with the arguments, the refs returned, scores, stage timings, index versions and your trace id. When an answer goes wrong, send us the trace id.

**Sending spans to Langfuse.** They go out over OTLP only when an endpoint is set, with OpenTelemetry's own settings, so the gateway depends on no tracing product. The gateway must run with the `otlp` extra, which the image and the development environment have.

```sh
export OTEL_EXPORTER_OTLP_ENDPOINT="$LANGFUSE_BASE_URL/api/public/otel"
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic%20$(printf %s "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" | base64 | tr -d '\n' | sed 's/=/%3D/g; s/+/%2B/g; s#/#%2F#g'),x-langfuse-ingestion-version=4"
uv run metamorph-gateway serve
```

| In Langfuse | What it shows |
|---|---|
| Type | `retriever` for a search, `tool` for anything else |
| Input | The call's arguments |
| Output | The refs returned, with their scores |
| Level | `ERROR` for a failed call. `WARNING` for one that answered but was degraded, such as results not reranked; the reason is the status message |
| Metadata | `result_count`, `top_score`, `index_versions`, `empty_reason`, `warnings`, `call_id`, all filterable |
| Children | One span per stage, timed as it ran |

- **Questions stay out of traces by default.** Any argument text holding a space becomes `[redacted]`, the same rule as mira-ai-chatbot's. Set `METAMORPH_RETRIEVAL_TRACE_CONTENT=full` to keep them, only for a Langfuse that may store user text.
- **Tracing never costs an answer.** Spans go in batches on their own thread, and a failed export only logs. The last batch is sent when the server stops.
- **Calling `Gateway` in process records nothing,** as `gateway_from_environment` does: spans belong to the catalog, which `metamorph-gateway serve` runs. To trace an evaluation run, serve the gateway and evaluate through its client ([eval/README.md](../eval/README.md)).
- **Reading traces back:** Langfuse 4 runs `events_only`, so `/api/public/traces` is gone. Use `/api/public/v2/observations?traceId=...&fields=core,basic,io,metadata`.

## Since the regulatory provider joined (M5)

- **`search_documents` searches regulations and fatwas too.** A search of every kind asks both providers at once and fuses their rankings by rank (a provider's scores mean nothing to the other's). A search for kinds one provider holds (`kinds: ["regulation"]`) is that provider's alone. When one provider fails, the other's hits come back with a warning naming it.
- **A hit is a retrieval unit:** the smallest provision with wording of its own, such as a paragraph with its lettered items (`doc:ojk:pojk:2024:40#pasal-137/ayat-3`), or an article without paragraphs. An article holding paragraphs, or one item, is never a hit, but `read` serves any published address, the same refs the stand-in served before.
- **It matches words and meaning,** fused by rank, and `matched_by` says which found a hit. Words find what a question turns on (an amount, a term, a number); meaning finds the rest, across languages.
- **The regulatory index is a snapshot,** rebuilt after a publish (`scripts/refresh-regulation-index.sh`). Reads of `doc:` refs come from it, so a regulation published since the last build isn't there yet.
- **`follow_links` answers for both layers, merged.**
  - **Order:** what changes the text comes first, so "is this still the rule?" is answered on the first page. The two layers then take turns, the owner of the ref first.
  - **A document's links** are those with other documents.
  - **A provision's links** also hold the references inside its document, and what changes the article or the document holding it. A paragraph of a revoked regulation shows what revoked the regulation.
  - **`effective_on`** is the date the document stating the link took effect. **`confidence`** is 0.9 where a source states the link, 0.6 where it was found by pattern in the text.
  - **A link may name a regulation that isn't published.** Reading that ref gives `unknown_ref`.
- **Reading a regulation** (`read` on a `doc:` ref without an address) gives its `status_history`: each status a source gave the whole document, with its date when known. It covers a revocation no link explains. It also gives the document's `outline`: a list of groups `{heading, units, titles?}` in reading order. `units` are addresses such as `pasal-10`, read as this doc ref plus `#address`; `titles` gives a unit's own heading where it has one, such as a romawi or a diktum. `outline_reading` says in one sentence how to read a unit. The index build writes the outline into the meta table's `outline` column, so an index built before it has none and reads as before.
