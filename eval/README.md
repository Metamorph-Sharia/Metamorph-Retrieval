# Evaluation sets

Retrieval is judged on its own, apart from the agent's answers, so that "retrieval missed it" can be told from "the agent asked badly" (`docs/retrieval-architecture.md` §8, in Metamorph-Knowledge-Platform). Each set is a JSON Lines file of cases, run by `metamorph-eval` (`packages/metamorph-retrieval-eval`).

| Set | Cases | What |
|---|---|---|
| [`market/cases.jsonl`](market/cases.jsonl) | 54 | The market provider: companies, industry context, figures, series, report and release passages, links, reading, errors |

## A case

```json
{"id": "companies-licensed-sharia-p2p", "phase": "industry",
 "question": "Which sharia P2P lenders does OJK license today?",
 "tool": "find_companies", "arguments": {"register": "ojk:lpbbti", "business_type": "sharia", "status": "licensed", "limit": 25},
 "expect": {"refs": ["company:ojk:lpbbti:kep-21-d.05-2020", "…"], "match": "exact"},
 "basis": "published_market, 2026-10-30: company where business_type = sharia and status = licensed: 7"}
```

- **`question`** is phrased as a user would ask it. Friend 1 can use it to evaluate the agent's choice of tool and arguments.
- **`tool` and `arguments`** are the call a good agent would make, in the agent's tool catalog. The case judges what retrieval returns for that call.
- **`phase`** is the customer journey's: `macro`, `industry`, `product`, `compliance`.
- **`expect`** lists what the call should return:
  - **`refs`** under **`match`:**
    - `exact`: these items and no others, in any order. For exact tools.
    - `all`: each one in the first `k` (8 by default).
    - `any`: at least one in the first `k`. For broad questions that many passages answer.
    
    An expected ref without an address (a whole report) is found by any of its passages.
  - **`names`:** refs the returned items must name in their fields, e.g. an industry's regulations or a company's announcements.
  - **`figures`:** a series' value for a period, and its provisional mark when given.
  - **`error`:** the error code the call should raise instead.
- **`basis`** says why: the query that found the evidence, or the passage read.

**How the market set was built** (2026-10-30):
- **Exact cases** come from SQL queries on `published_market`.
- **Search cases** come from passages found by distinctive phrases, then read before they were accepted.
- **Every expected ref and figure was checked against the live database:** 99 refs, all present, and every figure equal to its stored value.

When the data changes, `metamorph-eval run` lists any expected ref the provider no longer holds.

## Runs

| Run | Passed | Recall@k | MRR | Notes |
|---|---|---|---|---|
| [2026-10-30, M2 (SQL only)](market/runs/2026-10-30-m2.md) | 32 of 54 | 0.58 | 0.53 | Every exact case passes (companies, figures, links, reads, errors). `search_documents` waits for M4's index (18 cases). `industry_context` and `find_series` miss three English queries, which need meaning rather than words |
| [2026-10-30, M3 (through the gateway, over HTTP)](market/runs/2026-10-30-m3.md) | 32 of 54 | 0.58 | 0.53 | The same, end to end: client → HTTP → gateway → market provider and regulation stand-in. Identical to M2 case by case |
| [2026-10-30, M4 (search: full text + bge-m3, `market-2026-10-30.6`, through the gateway)](market/runs/2026-10-30-m4.md) | 52 of 54 | 0.89 | 0.82 | `search_documents` 18 of 19 (full text alone: 17, recall 0.68 → 0.74); `industry_context` 4 of 4 and `find_series` 8 of 9 with meaning. Activated by [the gate](market/runs/2026-10-30-m4-gate.md); [how the model and floor were chosen](market/runs/2026-10-30-m4-models.md) |

**Activating an index version** (§8): run the set on the active version and on the candidate (`METAMORPH_MARKET_INDEX_VERSION`), then `metamorph-eval compare active.json candidate.json`. It exits 0 only if the candidate passes at least as many cases and recalls at least as much, and lists the cases gained and lost. `scripts/refresh-market-index.sh` does all of it after each publish, through the `market_index` DAG.

**One case to review:** `series-sharia-third-party-funds` asks for sharia banks' third-party funds, and expects sharia commercial banks only. Rural sharia banks (BPRS) are sharia banks too, and their third-party funds rank first. The question, or its expected refs, should say which it means.

## Measures

- **Recall@k:** the share of expected refs in the first `k`.
- **Reciprocal rank:** 1 over the rank of the first expected ref, measured over the first `k` (over every item for an exact tool).
- **Passed:** the case's `match`, `names`, `figures` or `error` all hold.

The report gives these for all cases, for each tool and for each phase. It lists every failure with its reasons, and the expected refs the provider doesn't hold. An index version is activated only if the report is no worse than the active version's (§8).

## Running

```sh
uv run metamorph-eval check eval/market/cases.jsonl
uv run metamorph-eval run eval/market/cases.jsonl --provider some.module:factory \
    --title "Market, index market-2026-11-05.1" --markdown report.md --json report.json
uv run metamorph-eval compare active.json candidate.json     # the activation gate
```

`--provider` names any function that builds a provider with no arguments: a provider's own (`metamorph_market_retrieval.wiring:market_provider`), or the gateway's client (`metamorph_retrieval_gateway.client:from_environment`, with `METAMORPH_RETRIEVAL_GATEWAY_URL`).

## What the market tools must return (for M2)

The cases fix these conventions. The market provider's tools follow them:

- **Every tool returns a page:**
  - ranked tools (`find_series`, and `find_companies` with a `query`) return a page of hits, as `search` does;
  - exact tools return the contract's `evidence_page`.
  
  The items' refs are what the tool returned.
- **What an item names, it names as `{"ref": "…"}` in its record's fields,** e.g. `{"governed_by": [{"ref": "doc:ojk:pojk:2024:40"}]}`. The gateway enriches those stubs with citations later.
- **Arguments:**

  | Tool | Arguments |
  |---|---|
  | `find_companies` | `register`, `query`, `status`, `business_type`, `as_of`, `announcements`, `limit` |
  | `industry_context` | `query` |
  | `find_series` | `query` |
  | `get_observations` | `series` (series refs), `from`, `to` (periods: `2026-08`, `2026-Q2`, `2025`) |
  | `follow_links` | `ref`, `direction`, `types`, `limit`, as the contract's links request |
  | `read` | `ref`, `window` |

- **An industry's ref** is `industry:{source}:{slug}`. The slug is its name in lower case, with every run of other characters turned into a hyphen, e.g. `industry:ojk:portal:bank-umum-syariah`.
- **A figure's `period`** is written as the case writes it: `2026-08`, `2026-Q2`, `2025`.
