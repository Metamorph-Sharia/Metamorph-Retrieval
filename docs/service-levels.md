# Retrieval service levels

Status: provisional internal agreement. Retrieval provides search, exact reads, links and regulation changes to Chatbot, using the published regulation and market data from Knowledge Platform. Measure the gateway that MIRA calls, currently documented as `retrieval-gateway-dev`. The Retrieval owner leads incidents on this path and brings in Knowledge Platform for missing publications or Chatbot for consumer-side failures. The named owner, backup and alert route are pending confirmation. See the [MIRA measurement and error-budget policy](../../mira-ai-chatbot/docs/MIRA_SERVICE_LEVELS.md).

## Indicators and objectives

| SLI | Eligible unit and good outcome | Provisional SLO | Measurement source |
| --- | --- | --- | --- |
| Search availability | One valid search tool call. Good when every provider required by the request contributes a valid result, including a genuine empty match. | ≥99.5% over 28 days | Caller outcomes for edge failures and timeouts, correlated with call spans for provider outcomes and warnings. |
| Exact read availability | One valid read for a reference expected to be readable in the active index. Good when the requested text or metadata required by the tool is returned. | ≥99.5% over 28 days | Caller and gateway outcomes by tool. Probe a known reference and validate response content. |
| Search and exact read latency | Elapsed time from caller dispatch through receipt and decoding of a successful tool result. | Search p95 ≤15 s and exact read p95 ≤1 s over 28 days | Caller duration for the MIRA route. Use gateway provider and reranker spans for diagnosis. |
| Index activation on time | One eligible published change affecting a Retrieval index. Good when a live, queryable snapshot reflects that revision or a superseding revision within 24 hours of publication. | ≥90% per index over 90 days | Join publication and activation records by revision. Validate index visibility through the gateway manifest and a content-aware read or query. |
| Regulation reader freshness | One eligible published regulation or revision. Good when a production-path check can open the published version in the Mira iOS reader within 24 hours of publication. | ≥90% over 90 days | Join publication records to a reader-path check using the regulation reference and expected revision or content fingerprint. Use the iOS journey probe to validate the user path. |

For a read of a newly published regulation still awaiting activation, record the pending freshness outcome and surface the downstream reader impact. A missing reference in an active index that should contain it fails exact read availability. A documented `unknown_ref` for an unknown or unpublished reference is an expected response. A partial federated result missing a requested provider fails the search SLI even when the transport succeeded. When a search meets the contract in fused order, record `NOT_RERANKED` as degraded and report its rate separately. Track links and `list_changes` independently in the operational dashboard so search volume cannot obscure failures in the Watch path.

An index rejected by the evaluation gate stays in the activation and freshness cohorts. Keep the previous snapshot available, diagnose the regression, and preserve the rejected and active revision IDs. The approved evaluation gate remains the release condition. A manifest timestamp alone cannot establish that a specific revision is readable.

## Retrieval service agreement and quality objectives

Retrieval provides the Chatbot with ranked evidence and exact reference lookups. Its operational commitments are the 28-day search and exact-read availability and latency objectives above. Use the same MIRA gateway route for quality evaluation. For a fixed query test, pin the tool, arguments, expected references, and source versions. This measures Retrieval independently of how the Chatbot chooses or phrases a search.

| Quality SLI | Definition | Provisional SLO |
| --- | --- | --- |
| Regulation golden evidence coverage | Mean Recall@8 across golden search cases. For each case, divide the number of required evidence references found among the first eight results by the number of labeled required references, then average the case scores. | ≥50% |
| Regulation golden ranking | Mean reciprocal rank across the same cases. Score each case as `1 ÷ rank` of the first matching reference among the first eight, or zero if none is found. | ≥0.38 |
| Regulation corpus case pass rate | Passed cases divided by all cases in the corpus suite, using each case's expected reference and rank rules. | ≥85% |
| Market case pass rate | Passed cases divided by all market-suite cases, checking the expected references, names, figures and specified outcomes as applicable. | ≥95% |
| Federated case pass rate | Passed cases divided by all federated-suite cases, including required evidence across providers. | ≥85% |
| Exact reference correctness | Correct lookups divided by all checks for verified indexed references. A correct lookup returns the exact requested reference and the expected text or data. | 100% |
| Blind holdout performance | Report case pass rate, Recall@k, and mean reciprocal rank for the untuned regulation holdout. | Set after a baseline on MIRA's production route |

Report each suite with case counts, applicable score denominators, snapshot and reranker version. Keep expected-empty cases distinct from provider failures. When relevant, report degraded results without reranking separately. Use a verified exact-reference fixture that checks the returned text or values. Reference matching in search can accept a related passage according to the search rubric, while the exact-reference fixture verifies the requested address itself.

Compare the candidate and current versions using the same cases for each material change to search, ranking or the index, and diagnose newly lost cases. Preserve the existing activation gates for the configured market and regulation suites, which compare overall passes and recall. Block release for a newly confirmed critical error, such as returning the wrong applicable provision for a verified exact reference. Track other misses against the provisional targets during review. Preserve the blind holdout by using separate cases for tuning.

## Evidence and response

The November 10 public gateway check recorded search p50 6.6 s and p95 10.3 s, with one exact read at 163 ms. The regulation golden set scored 0.51 recall and 0.38 mean reciprocal rank. The same run passed 55 of 64 corpus, 52 of 54 market and 24 of 27 federated cases. These are historical benchmarks for the configuration tested. Establish a fresh quality baseline and 28-day operational baseline. Langfuse spans include result counts, errors, warnings, provider and reranker timing, and index versions. `/health` indicates that the gateway is responding. Use `/manifest`, known-record reads and a federated search probe to cover dependencies and result quality.

Before approving targets, confirm the configured MIRA route, stable recording of publication and live revision IDs, and coverage of failed calls before the gateway receives them. Test a provider outage, partial federation, a missed activation deadline and a stale reader result. Alert Retrieval on-call on gateway budget burn or overdue activation and hand off upstream publication gaps to Knowledge Platform.

[Gateway contract and tracing](connecting-an-agent.md) · [Deployment, evaluation and rollback](deploying.md) · [Evaluation suites and scoring](../eval/README.md)
