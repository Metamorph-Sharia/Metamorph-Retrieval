# Evaluation sets

Retrieval is judged on its own, apart from the agent's answers, so that "retrieval missed it" can be told from "the agent asked badly" (`docs/retrieval-architecture.md` §8, in Metamorph-Knowledge-Platform). Each set is a JSON Lines file of cases, run by `metamorph-eval` (`packages/metamorph-retrieval-eval`).

| Set | Cases | What |
|---|---|---|
| [`market/cases.jsonl`](market/cases.jsonl) | 54 | The market provider: companies, industry context, figures, series, report and release passages, links, reading, errors |
| [`regulation/cases.jsonl`](regulation/cases.jsonl) | 42 | Regulation search: mira-ai-chatbot's golden questions, asked as they are, for the retrieval units each answer needs (54 refs) |

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

**How the regulation set was built** (2026-11-03):
- **The questions are mira-ai-chatbot's golden set** (`data/evaluation/golden_queries_50_v4_1.jsonl`), so retrieval is judged on what the answering agent is judged on. Each case asks `search_documents` with the question as it is and `in_force_on` its reference date; `match` is `all`.
- **Expected refs are the retrieval units the golden answer requires,** since a `doc:` ref's address is a unit's (`published.provision_unit`, the contract).
  - The golden labels a clause; the unit is that clause, or the unit holding it: a lettered item is inside its paragraph (`pasal-3/ayat-6/huruf-a` is `pasal-3/ayat-6`). An SEOJK part or a fatwa's decision is one unit, its numbered items within it.
  - An article split into paragraphs is the paragraph its snippet quotes.
  - A golden label that names a published provision is used as it is. Where the golden snippet paraphrases its clause, the clause was read to confirm it.
- **Ten labels were mapped by hand.** In each, the label doesn't name, on the platform, the provision its snippet quotes: fatwas the platform numbers differently, POJK 22/2023's exoneration clause (Pasal 46, not 23), and SEOJK parts the snippet quotes one item of. Each case's `basis` says which and why.
- **Left out:**
  - eight questions with no regulatory evidence: four that should be refused (nothing on the platform answers them, one of them naming a Permenaker the platform doesn't publish), three market questions;
  - GOLDEN-013, whose fatwa (8/2000) has no decision wording on the platform.
- **Every expected clause was in force on its question's date,** so `in_force_on` excludes none.
- **Five refs are in UU 27/2022 (personal data protection),** which the index left out until 2026-11-03. The runs before that date can't find them.

## Runs

| Run | Passed | Recall@k | MRR | Notes |
|---|---|---|---|---|
| [2026-10-30, M2 (SQL only)](market/runs/2026-10-30-m2.md) | 32 of 54 | 0.58 | 0.53 | Every exact case passes (companies, figures, links, reads, errors). `search_documents` waits for M4's index (18 cases). `industry_context` and `find_series` miss three English queries, which need meaning rather than words |
| [2026-10-30, M3 (through the gateway, over HTTP)](market/runs/2026-10-30-m3.md) | 32 of 54 | 0.58 | 0.53 | The same, end to end: client → HTTP → gateway → market provider and regulation stand-in. Identical to M2 case by case |
| [2026-10-30, M4 (search: full text + bge-m3, `market-2026-10-30.6`, through the gateway)](market/runs/2026-10-30-m4.md) | 52 of 54 | 0.89 | 0.82 | `search_documents` 18 of 19 (full text alone: 17, recall 0.68 → 0.74); `industry_context` 4 of 4 and `find_series` 8 of 9 with meaning. Activated by [the gate](market/runs/2026-10-30-m4-gate.md); [how the model and floor were chosen](market/runs/2026-10-30-m4-models.md) |

**Regulation runs** (k = 8; a local build of the index from the platform's published data, 576,988 provisions, 179,325 of them searchable units; 2026-11-03):

| Run | Passed | Recall@k | MRR | Notes |
|---|---|---|---|---|
| mira-ai-chatbot's `PostgresRAGClient` (full text), its first 8 | 3 of 42 | 4 of 54 refs | | The baseline. In the 25 it gives the model: 9 of 54 |
| [The provider as merged](regulation/runs/2026-11-03-as-merged.md): every provision searched, by meaning only | 6 of 42 | 0.15 | 0.09 | An article and its paragraphs, and an item and its paragraph, compete for the same places |
| [Retrieval units only, by words and meaning fused](regulation/runs/2026-11-03-units-words.md) | 12 of 42 | 0.31 | 0.12 | What the index builds now |
| [Through the gateway, market and regulation fused](regulation/runs/2026-11-03-gateway.md) | 9 of 42 | 0.21 | 0.05 | A search of every kind: market passages take some of the 8 places |
| [Through the gateway, fused and reranked](regulation/runs/2026-11-03-gateway-reranked.md) | 15 of 42 | 0.38 | 0.34 | The gateway's reranker (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, 50 candidates, 256 tokens) reads each candidate against the question, on one scale across providers. What runs on AWS |
| On AWS, inside the VPC (index `2026-11-03`, UU 27/2022 included; bf16 maths) | provider alone 13 of 42; gateway reranking 25 candidates 14 of 42 (what runs); 50 candidates 16 of 42 | | | Market set 52 of 54 either way. [docs/deploying.md](../docs/deploying.md) has the latency |

**How each change counted,** on the same vectors (2026-11-03):

| Searched | By meaning | By words and meaning |
|---|---|---|
| Every provision | 6 of 42, recall 0.15 | 5 of 42, recall 0.12 |
| Retrieval units only | 10 of 42, recall 0.25 | **12 of 42, recall 0.31** |

- **Words help only over units.** Over every provision they add articles and items to the crowd.
- **The word search's stop words are the corpus's own.** The `indonesian` configuration keeps every word, so stems in more than 5% of units (177 of them: yang and dan, but also pasal, ayat, wajib) don't pick candidates. Without that, a question took 4 s and over every provision timed out; with it, under 1 s. They still count once a unit is a candidate. Dropping them altogether cost a case (11 of 42).
- **A cross-encoder reranker** over the provider's first 50 hits, 256 tokens: bge-reranker-v2-m3 and the smaller multilingual `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` both found 21 of 54 refs instead of 15, and passed 17 cases instead of 12. The small one took 0.34 s a question on an M-series GPU and 0.87 s on 2 of its CPU threads, the large one 2.4 s on the GPU. The gateway runs the small one, on its task's CPU ([docs/deploying.md](../docs/deploying.md) says why).

The five UU 27/2022 refs can't be found until that law is indexed.

Through the fused gateway the market set still passes 52 of 54, the same cases as at M4, but `search_documents` recall drops from 0.74 to 0.70: its questions name no kinds, and regulations now share the 8 places. Ask with `kinds` to search one provider alone. With the reranker the market set still passes 52 of 54, and `search_documents` MRR rises from 0.67 (M4) to 0.72.

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
