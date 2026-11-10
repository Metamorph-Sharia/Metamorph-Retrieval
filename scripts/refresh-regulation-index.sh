#!/bin/sh
# Refresh the regulation index after a publish: build a new snapshot, judge it against the live one on the question
# sets, and activate it only if it is no worse on each (retrieval-architecture.md §6.6). The regulation_index DAG runs
# this, as market_index runs refresh-market-index.sh, and both judge with metamorph-eval through their provider.
#
#   METAMORPH_REGULATION_INDEX_URL      where the index lives (falls back to METAMORPH_DATABASE_URL, as Airflow has it)
#   METAMORPH_REGULATION_PUBLISHED_URL  the platform's published schema (default: the same database)
#   METAMORPH_REGULATION_MODEL          the embedding model (default bge_m3)
#   METAMORPH_REGULATION_CASES          the question sets, space-separated (default: the golden and corpus sets; the
#                                       holdout is never read)
#   METAMORPH_EVAL_REPORTS              where the runs and their comparisons are kept (default var/index-reports)
#
# A build takes the live build's vectors by chunk id, so it embeds only the new and changed chunks. The first build has
# nothing to be judged against and is activated as built.
#
# Exits 0 when the new snapshot is active (or nothing changed), 3 when it was built but kept inactive (worse), anything
# else on failure.
set -eu
export METAMORPH_REGULATION_INDEX_URL="${METAMORPH_REGULATION_INDEX_URL:-${METAMORPH_DATABASE_URL:?set METAMORPH_REGULATION_INDEX_URL}}"
export METAMORPH_REGULATION_PUBLISHED_URL="${METAMORPH_REGULATION_PUBLISHED_URL:-$METAMORPH_REGULATION_INDEX_URL}"
model="${METAMORPH_REGULATION_MODEL:-bge_m3}"
sets="${METAMORPH_REGULATION_CASES:-eval/regulation/cases.jsonl eval/regulation/corpus.jsonl}"
snapshot="${METAMORPH_REGULATION_SNAPSHOT:-$(date -u +%Y-%m-%dT%H%M%SZ)}"
reports="${METAMORPH_EVAL_REPORTS:-var/index-reports}/$snapshot"
provider="metamorph_regulation_retrieval.wiring:regulation_provider"

if [ "${METAMORPH_REGULATION_FORCE:-}" != "1" ] && metamorph-regulation-index current; then
    echo "unchanged since the live build; nothing to do"
    exit 0
fi
live=$(metamorph-regulation-index versions | awk '$2 == "live"' | head -n 1)

mkdir -p "$reports"
echo "building $snapshot"
metamorph-regulation-index build --snapshot "$snapshot" --model "$model"

if [ -z "$live" ]; then
    metamorph-regulation-index activate --snapshot "$snapshot"
    echo "activated $snapshot: the first build, with none to judge it against"
    exit 0
fi

worse=""
for cases in $sets; do
    name=$(basename "$cases" .jsonl)
    metamorph-eval run "$cases" --provider "$provider" --title "live" --markdown "$reports/$name-live.md" \
        --json "$reports/$name-live.json"
    env $(metamorph-regulation-index tables --snapshot "$snapshot") metamorph-eval run "$cases" --provider "$provider" \
        --title "$snapshot" --markdown "$reports/$name-$snapshot.md" --json "$reports/$name-$snapshot.json"
    rc=0
    metamorph-eval compare "$reports/$name-live.json" "$reports/$name-$snapshot.json" \
        --markdown "$reports/$name-comparison.md" || rc=$?
    if [ "$rc" -eq 3 ]; then
        cat "$reports/$name-comparison.md"
        worse="$worse $name"
    elif [ "$rc" -ne 0 ]; then
        exit "$rc"
    fi
done

if [ -n "$worse" ]; then
    echo "$snapshot kept inactive: worse than the live snapshot on$worse" >&2
    exit 3
fi
metamorph-regulation-index activate --snapshot "$snapshot"
echo "activated $snapshot"
