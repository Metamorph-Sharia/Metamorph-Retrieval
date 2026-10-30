# Metamorph Retrieval

The retrieval layer of the market entry platform. It gives an answering agent evidence, never answers. The design is `docs/retrieval-architecture.md` in Metamorph-Knowledge-Platform:
- **providers** each own an index over the platform's read contracts;
- they speak **one contract**;
- a **gateway** composes them for the agent over MCP and HTTP.

| Package | What | Status |
|---|---|---|
| [`metamorph-retrieval-contract`](packages/metamorph-retrieval-contract/RETRIEVAL_CONTRACT.md) | Refs, evidence, the provider protocol, the JSON Schema, a conformance check | 0.1 (M0) |
| [`metamorph-retrieval-eval`](eval/README.md) | Question sets with expected evidence, a runner and its report, and the gate comparing two runs (`metamorph-eval`) | 0.1 (M1, compare M4) |
| `metamorph-market-retrieval` | The market provider over `published_market`: search over report and release passages (full text + embeddings, fused), companies (today or on a past date), industry context, series and their figures, links, reading any market ref; its index in `retrieval_market` (`metamorph-market-index`) | 0.1 (M2, search M4) |
| [`metamorph-retrieval-gateway`](docs/connecting-an-agent.md) | The providers as one: routing, time budgets, citations for what records name, MCP and HTTP, the call log and traces (`metamorph-gateway`) | 0.1 (M3); merging several providers' searches and links in M5 |
| `metamorph-regulation-standin` | Reads and describes regulations (`doc:` refs) from `published` until Friend 2's provider arrives; never searches | 0.1 (M3) |

## Develop

```sh
uv sync
uv run pytest                    # offline; the PostgreSQL read-model tests are skipped
METAMORPH_RETRIEVAL_TEST_DATABASE_URL=postgresql://metamorph:metamorph-dev@localhost:5433/postgres uv run pytest
                                 # + those tests, on a throwaway database each run
uv run ruff check .
```

Run the market question set against the platform's live data (read only):

```sh
METAMORPH_RETRIEVAL_DATABASE_URL=postgresql://metamorph:metamorph-dev@localhost:5433/metamorph \
  uv run metamorph-eval run eval/market/cases.jsonl --provider metamorph_market_retrieval.wiring:market_provider
```

Build the market's search index (writes only the `retrieval_market` schema; needs the `embeddings` extra, installed by `uv sync`):

```sh
export METAMORPH_RETRIEVAL_DATABASE_URL=postgresql://metamorph:metamorph-dev@localhost:5433/metamorph
uv run metamorph-market-index prepare                    # once: the schema and pgvector
uv run sh scripts/refresh-market-index.sh                # build with bge-m3, judge it, activate it if no worse
uv run metamorph-market-index versions
```

Serve the gateway, for an agent (MCP at `/mcp`) or any HTTP client ([docs/connecting-an-agent.md](docs/connecting-an-agent.md)):

```sh
METAMORPH_RETRIEVAL_DATABASE_URL=postgresql://metamorph:metamorph-dev@localhost:5433/metamorph \
  uv run metamorph-gateway serve --port 8765        # --host 0.0.0.0 to serve other machines
```

and run the question set through it, end to end:

```sh
METAMORPH_RETRIEVAL_GATEWAY_URL=http://127.0.0.1:8765 \
  uv run metamorph-eval run eval/market/cases.jsonl --provider metamorph_retrieval_gateway.client:from_environment
```

**The rules every package keeps:**
- **Clean Architecture,** with dependencies pointing inward. The contract imports only the standard library and `jsonschema`.
- **No generative model at query time.** Query rewriting, grading and answering are the agent's.
- **Tests first, in small steps.**
