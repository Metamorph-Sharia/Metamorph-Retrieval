#!/bin/sh
# Refresh the regulation index after a publish: build a new snapshot, judge it against the active one on the
# question set, and activate it only if it is no worse (retrieval-architecture.md §6.6). The regulation_index DAG
# runs this.
#
#   METAMORPH_REGULATION_INDEX_URL   where the index lives (falls back to METAMORPH_DATABASE_URL, as Airflow has it)
#   METAMORPH_REGULATION_PUBLISHED_URL  the platform's published schema (default: the same database)
#   METAMORPH_REGULATION_MODEL       the embedding model (default bge_m3)
#   METAMORPH_REGULATION_CASES       the question set (default eval/regulation/cases.jsonl)
#   METAMORPH_EVAL_REPORTS           where the judgement is kept (default var/index-reports)
#
# Exits 0 when the new snapshot is active (or nothing changed), 3 when it was built but kept inactive, anything
# else on failure.
set -eu
export METAMORPH_REGULATION_INDEX_URL="${METAMORPH_REGULATION_INDEX_URL:-${METAMORPH_DATABASE_URL:?set METAMORPH_REGULATION_INDEX_URL}}"
export METAMORPH_REGULATION_PUBLISHED_URL="${METAMORPH_REGULATION_PUBLISHED_URL:-$METAMORPH_REGULATION_INDEX_URL}"
model="${METAMORPH_REGULATION_MODEL:-bge_m3}"
cases="${METAMORPH_REGULATION_CASES:-eval/regulation/cases.jsonl}"
snapshot="${METAMORPH_REGULATION_SNAPSHOT:-$(date -u +%Y-%m-%dT%H%M%SZ)}"
reports="${METAMORPH_EVAL_REPORTS:-var/index-reports}/$snapshot"

if [ "${METAMORPH_REGULATION_FORCE:-}" != "1" ] && metamorph-regulation-index current; then
    echo "unchanged since the live build; nothing to do"
    exit 0
fi

mkdir -p "$reports"

echo "building $snapshot"
metamorph-regulation-index build --snapshot "$snapshot" --model "$model"

echo "judging $snapshot against the active snapshot"
if metamorph-regulation-index judge --cases "$cases" --snapshot "$snapshot" --model "$model" \
        --json "$reports/judgement.json"; then
    metamorph-regulation-index activate --snapshot "$snapshot"
    echo "activated $snapshot"
else
    status=$?
    if [ "$status" -eq 3 ]; then
        echo "$snapshot kept inactive: worse than the active snapshot" >&2
    fi
    exit "$status"
fi
