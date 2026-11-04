# Evaluation sets

Retrieval is judged on its own, apart from the agent's answers, so that "retrieval missed it" can be told from "the agent asked badly" (`docs/retrieval-architecture.md` §8, in Metamorph-Knowledge-Platform). Each set is a JSON Lines file of cases, run by `metamorph-eval` (`packages/metamorph-retrieval-eval`).

| Set | Cases | What |
|---|---|---|
| [`market/cases.jsonl`](market/cases.jsonl) | 54 | The market provider: companies, industry context, figures, series, report and release passages, links, reading, errors |
| [`regulation/cases.jsonl`](regulation/cases.jsonl) | 42 | Regulation search: mira-ai-chatbot's golden questions, asked as they are, for the retrieval units each answer needs (54 refs) |
| [`regulation/corpus.jsonl`](regulation/corpus.jsonl) | 64 | Regulation search across the corpus: units drawn at random from every kind of instrument. Open to reading and tuning |
| [`regulation/holdout.jsonl`](regulation/holdout.jsonl) | 36 | The same draw, kept apart: its failures aren't read and nothing is tuned on it, so it stays a blind check |
| [`federated/cases.jsonl`](federated/cases.jsonl) | 27 | Both layers together: links between regulations and to what OJK said of them, a rule and what the regulator said of it, and the hops from an industry to its rules |

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

**How the federated set was built** (2026-11-04):
- **Link cases come from the regulations' own wording,** not the link table: each expected link was read in the provision stating it, such as POJK 40/2024 Pasal 236 revoking POJK 10/2022. Four kinds were left out because the wording couldn't confirm them: `implements`, `adopts_fatwa`, a link to an unpublished document, and `changes_fatwa`, which has no links yet.
- **Search cases pair a rule with what a regulator said of it.** Each passage was read before it was accepted.
- **A question of two parts is two calls.** Each of the first six search cases asked for a rule and what OJK said of it in one search: 1 of 6 passed, the two halves' words competing for the same places. Asked as two searches, as a case's call is meant to be the one a good agent makes, those topics give the 11 search cases below. Splitting a question is the agent's (`docs/retrieval-architecture.md` §2), so a two-part search is no gate here.
- **Rule cases set `in_force_on`,** as a good agent would. Without it, POJK 5/2015 outranked POJK 7/2026, which replaced it.
- **The cases were written after a first look at results,** so the search cases' pass rate is not a blind measure. The two that fail were kept as they fail.

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
| [Through the gateway, fused and reranked](regulation/runs/2026-11-03-gateway-reranked.md) | 15 of 42 | 0.38 | 0.34 | The gateway's reranker (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, 50 candidates, 256 tokens) reads each candidate against the question, on one scale across providers. On AWS the gateway reranks 25 candidates (below) |
| On AWS, inside the VPC (index `2026-11-03`, UU 27/2022 included; bf16 maths) | provider alone 13 of 42; gateway reranking 25 candidates 14 of 42 (what runs); 50 candidates 16 of 42 | | | Market set 52 of 54 either way. [docs/deploying.md](../docs/deploying.md) has the latency |
| Index before the context change, local, UU 27/2022 included: [25 candidates](regulation/runs/2026-11-04-before-context-25.md), [50](regulation/runs/2026-11-04-before-context-50.md) | 14 of 42; 16 of 42 | 0.36; 0.43 | 0.31; 0.38 | The same scores as on AWS, so the row below compares directly with what runs |
| Citation and headings embedded, local: [25 candidates](regulation/runs/2026-11-04-context-25.md), [50](regulation/runs/2026-11-04-context-50.md) | **16 of 42; 19 of 42** | **0.45; 0.49** | **0.39; 0.39** | See below. Not on AWS |

**Embedding what places a unit** (2026-11-04). The model used to read a unit's title, its address and its own wording. It now reads the document's citation and the headings above the unit too, so a paragraph that never names its regulation or topic can be found by them. The word search reads them as well. A small fix went in with it: "dihapus" or "cukup jelas" anywhere in a unit used to drop it from search, and now only when it says little else (2,197 units return).

| | Before | After |
|---|---|---|
| Gateway, 25 candidates | 14 of 42 | 16 of 42: 2 gained, 0 lost |
| Gateway, 50 candidates | 16 of 42 | 19 of 42: 4 gained, 1 lost (golden-016, from 2nd to 9th) |
| Provider alone | 13 of 42, MRR 0.14 | 14 of 42, MRR 0.23: 2 gained, 1 lost |
| Expected refs by meaning, in the first 50 | 24 of 54 | 30 of 54 |
| Expected refs in neither search's first 200 | 20 of 54 | 15 of 54 |
| Market set, 25 candidates | 52 of 54 | 52 of 54, the same cases |
| Federated set, 25 candidates | 25 of 27 | 25 of 27, the same cases |

- **On these 42 questions alone, the gained and lost cases can't be told from chance,** though by meaning 24 refs rank higher and 8 lower (sign test p = 0.007). The wider sets below settle it.
- **An earlier test promised more.** It re-embedded a pool of 10,060 units and translated the English questions, and went from 17 to 23 of 39. Units outside the pool couldn't compete, so that test overstated the gain.
- **Some units lose.** Of the 8 refs that rank lower by meaning, UU 27/2022's Pasal 20 ayat (2) fell from 9th to 99th, and two left the first 200 (golden-010, from 53rd; golden-034, from 112th). Those cases failed before too, so no score shows it. Why they fell wasn't looked into.
- **It costs a full re-embedding,** and the seed vectors of earlier builds no longer apply ([docs/deploying.md](../docs/deploying.md)).

**The corpus and holdout sets** (2026-11-04). The golden questions cover little of the corpus: 32 of their 54 refs are in POJK 40/2024, and most kinds of instrument never appear. No usage logs exist to draw on, so these 100 cases were written from the corpus, by Claude, under rules fixed before any result was seen.

- **The draw:** seeded (20261104), in nine groups, at most one unit a document, from units `in_force_on` 2026-11-04 keeps. The groups' sizes are a choice: POJK 22, SEOJK 12, PBI 12, PADG 10, SEBI 5, fatwa 12, UU 10, PP 5, others 12.
- **The question's style was drawn too,** per unit, so easy forms couldn't be favoured: language (English 42 of 100, more than the golden set's 26%), whether it names its regulation (54), and direct or a scenario (52 scenarios). The check in the build confirmed every question follows its draw.
- **Accepted in drawn order:** 130 units were read and 30 rejected as nothing a practitioner could ask of them alone: repeals, signature blocks, delegations, bare cross-references, forms, tables of contents. A list of definitions was rejected unless the question names its regulation.
- **Expected refs:** the drawn unit, one per case. A question that doesn't name its regulation also accepts units in force elsewhere with nearly the same wording (word-trigram Jaccard of 0.6 or more; 2 cases).
- **The split:** 35% of each group, seeded, into the holdout. The 42 golden cases stay in their own file, so their scores stay comparable, and because they've been looked at too often to be blind.

Through the gateway, local index, before and after embedding the citation and headings:

| Set | 25 candidates | Recall, MRR at 25 | 50 candidates |
|---|---|---|---|
| [Golden](regulation/runs/2026-11-04-context-25.md), 42 | 14 → 16 (+2, −0) | 0.36 → 0.45, 0.31 → 0.39 | 16 → 19 (+4, −1) |
| [Corpus](regulation/runs/2026-11-04-corpus-context-25.md), 64 | 47 → 55 (+8, −0) | 0.73 → 0.86, 0.57 → 0.67 | 50 → 56 (+7, −1) |
| [Holdout](regulation/runs/2026-11-04-holdout-context-25.md), 36 | 32 → 33 (+1, −0) | 0.88 → 0.90, 0.74 → 0.74 | 32 → 32 (+0, −0) |

- **The change holds up.** All 100 new questions were written after it was built, so they're a fresh test of it: 79 → 88 at 25 candidates, 9 gained and none lost (sign test p = 0.004). At 50, 82 → 88, 7 gained and 1 lost (p = 0.07).
- **The holdout alone shows little,** because it began at 32 of 36 and only 4 cases could rise. Its higher start is within what a random split gives (Fisher p = 0.08).
- **Don't average these sets, or read 88 of 100 as how the system does.** The golden set is much harder: its questions need several clauses (1 of 11 pass) or inference, and crowd one densely covered topic (single-clause cases pass 15 of 31). A random unit is often on a niche topic with few rivals. The new questions were also written by someone who had read the answer, though the corpus set shares no more words with its answers than the golden set does (a median 0.36 of a question's words for both; 0.50 for the holdout). The golden set shows depth, these sets breadth.
- **The citation seems to have done most of it.** Of the 100, questions naming their regulation went 44 → 52 of 54, and those that don't 35 → 36 of 46. Citation and headings went in together, so this is suggestive only: telling them apart takes another full build.
- **Where it still fails** (the 100, after, 25 candidates):

  | Questions | Passed |
  |---|---|
  | Indonesian | 56 of 58 |
  | English | 32 of 42 |
  | Name their regulation | 52 of 54 |
  | Don't | 36 of 46 |
  | Direct | 43 of 48 |
  | Scenario | 45 of 52 |

  By group, SEOJK (8 of 12) and fatwas (9 of 12) are lowest.
- **The corpus failures were read,** all 9. Seven are English. One is a false miss: `corpus-bi-sebi-04` found PADG 20/2025, which answers it as well as the expected unit. So a miss is usually a real one, and these scores are at most slightly low. In `corpus-bi-pbi-05` the same rule came back from another regulation, not the one the question names.
- **What these sets can't show:** questions needing several clauses, real users' wording, or answers that are out of date. A unit passing `in_force_on` may still have been changed by a later regulation.

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

Federated set:

| Run | Passed | Recall@k | MRR | Notes |
|---|---|---|---|---|
| [2026-11-04, through the gateway, 25 rerank candidates](federated/runs/2026-11-04-gateway.md) | 25 of 27 | 0.93 | 0.81 | Every link case passes, 13 of 13. Two searches miss, both real: the rule on minimum equity is asked as "pindar", a word only OJK's releases use; and "persyaratan perizinan penyelenggara" within POJK 40/2024 misses Pasal 10. Local index, without UU 27/2022 |

| [2026-11-04, on AWS, through the public development address](federated/runs/2026-11-04-aws-public.md) | 25 of 27 | 0.93 | 0.81 | The same result, on the live index with UU 27/2022 |

With links and merging in, the regulation set stays at 15 of 42 (50 candidates) and the market set at 52 of 54.

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
