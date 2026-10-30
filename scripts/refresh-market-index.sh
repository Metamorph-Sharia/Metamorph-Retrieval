#!/bin/sh
# Refresh the market index after a publish: build a new version, judge it against the active one on the question set,
# and activate it only if it is no worse (retrieval-architecture.md §6.6, §8). The market_index DAG runs this.
#
#   METAMORPH_RETRIEVAL_DATABASE_URL   the platform's database (falls back to METAMORPH_DATABASE_URL, as Airflow has it)
#   METAMORPH_MARKET_INDEX_MODEL       the embedding model (default BAAI/bge-m3)
#   METAMORPH_EVAL_CASES               the question set (default eval/market/cases.jsonl)
#   METAMORPH_EVAL_REPORTS             where the two runs and their comparison are kept (default var/index-reports)
#
# Exits 0 when the new version is active, 3 when it was built but kept inactive (worse), anything else on failure.
set -eu
export METAMORPH_RETRIEVAL_DATABASE_URL="${METAMORPH_RETRIEVAL_DATABASE_URL:-${METAMORPH_DATABASE_URL:?set METAMORPH_RETRIEVAL_DATABASE_URL}}"
model="${METAMORPH_MARKET_INDEX_MODEL:-BAAI/bge-m3}"
cases="${METAMORPH_EVAL_CASES:-eval/market/cases.jsonl}"
provider="metamorph_market_retrieval.wiring:market_provider"

built=$(metamorph-market-index build --model "$model")
version=$(printf '%s' "$built" | python -c 'import json, sys; print(json.load(sys.stdin)["version"])')
reports="${METAMORPH_EVAL_REPORTS:-var/index-reports}/$version"
mkdir -p "$reports"
echo "built $built"

metamorph-eval run "$cases" --provider "$provider" --title "active" --markdown "$reports/active.md" \
    --json "$reports/active.json"
METAMORPH_MARKET_INDEX_VERSION="$version" metamorph-eval run "$cases" --provider "$provider" --title "$version" \
    --markdown "$reports/$version.md" --json "$reports/$version.json"

if metamorph-eval compare "$reports/active.json" "$reports/$version.json" --markdown "$reports/comparison.md"; then
    metamorph-market-index activate "$version"
else
    status=$?
    cat "$reports/comparison.md"
    [ "$status" -eq 3 ] && echo "$version kept inactive: worse than the active version" >&2
    exit "$status"
fi
