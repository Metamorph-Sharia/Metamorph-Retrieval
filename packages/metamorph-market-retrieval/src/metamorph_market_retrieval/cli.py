"""`metamorph-market-index`: build index versions of the market's passages and dataset cards, and activate one.

    metamorph-market-index prepare                 the retrieval_market schema (and pgvector), once
    metamorph-market-index build --model BAAI/bge-m3
    metamorph-market-index build --words-only      full text alone: the baseline a model must beat
    metamorph-market-index versions
    metamorph-market-index activate market-2026-10-30.2

A build never activates. Compare the new version with the active one on the evaluation set first (`metamorph-eval
compare`, with METAMORPH_MARKET_INDEX_VERSION naming the candidate), and activate it only if it is no worse.
This session writes, but only retrieval_market; it reads published_market.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime

import psycopg

from metamorph_market_retrieval.adapters.embedder import MODELS, embedder_for
from metamorph_market_retrieval.adapters.index import PostgresIndexStore
from metamorph_market_retrieval.adapters.postgres import PostgresMarketReadModel
from metamorph_market_retrieval.application.building import ActivateIndex, BuildIndex
from metamorph_market_retrieval.wiring import database_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metamorph-market-index", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare", help="create the retrieval_market schema and the vector extension")
    build = commands.add_parser("build", help="build a new version; it isn't activated")
    model = build.add_mutually_exclusive_group(required=True)
    model.add_argument("--model", choices=sorted(MODELS))
    model.add_argument("--words-only", action="store_true")
    commands.add_parser("versions", help="list the versions, oldest first")
    activate = commands.add_parser("activate", help="make a version the active one")
    activate.add_argument("version")
    arguments = parser.parse_args(argv)

    with psycopg.connect(database_url(), autocommit=True) as connection:
        store = PostgresIndexStore(connection)
        if arguments.command == "prepare":
            store.prepare()
        elif arguments.command == "build":
            embedder = None if arguments.words_only else embedder_for(arguments.model)
            source = PostgresMarketReadModel(connection)
            built = BuildIndex(source, store, embedder, now=lambda: datetime.now(UTC)).run()
            print(json.dumps(built.__dict__))
        elif arguments.command == "versions":
            for version in store.versions():
                print(f"{version.version}  {version.state:8}  {version.units:5} units  {version.model or 'words only'}"
                      f"  built {version.built_at:%Y-%m-%d %H:%M}  from {version.source_published_at:%Y-%m-%d %H:%M}")
        else:
            ActivateIndex(store).run(arguments.version)
            print(f"{arguments.version} is active")
    return 0


if __name__ == "__main__":
    sys.exit(main())
