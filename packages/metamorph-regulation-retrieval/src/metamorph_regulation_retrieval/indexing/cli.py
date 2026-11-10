"""`metamorph-regulation-index`: build the regulation index, point an evaluation at a build, activate it.

    metamorph-regulation-index build --snapshot 2026-11-03
    metamorph-regulation-index build --snapshot 2026-11-03        taken from the live build, where it is the same model
    metamorph-regulation-index build --snapshot 2026-11-03 --vectors https://…   seeded with another build's vectors
    metamorph-regulation-index export-vectors --snapshot 2026-11-03 --to vectors.copy.gz
    metamorph-regulation-index tables --snapshot 2026-11-03   the settings that point the provider at a build
    metamorph-regulation-index activate --snapshot 2026-11-03
    metamorph-regulation-index versions

Exit codes: 0 ok, anything else a failure. `scripts/refresh-regulation-index.sh` builds, judges the build against the
live one with metamorph-eval (as the market's refresh does) and activates it only if it is no worse.
"""

from __future__ import annotations

import argparse
import json
import sys

import psycopg

from ..adapters.provider import INDEX_VERSION
from ..store import CHUNK_TABLE, EMBED_TABLE, META_TABLE
from . import build as builder
from .build import Tables
from .config import index_url, snapshot_id, table_name
from .embed import (
    MODELS,
    create_table,
    embed,
    export_vectors,
    import_vectors,
    index_vectors,
    load_model,
    open_vectors,
    seed_vectors,
)

LIVE = Tables("regulation_chunk_live", "regulation_emb_live", "regulation_meta_live")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metamorph-regulation-index", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="write a snapshot's chunks, metadata and vectors")
    build.add_argument("--snapshot", default=snapshot_id())
    build.add_argument("--model", default="bge_m3", choices=sorted(MODELS))
    build.add_argument("--limit", type=int, default=0, help="stop after N provisions, for a smoke build")
    build.add_argument("--skip-embed", action="store_true")
    build.add_argument("--vectors", default="", help="another build's vectors (export-vectors), a path or an https "
                       "URL: chunks they cover aren't embedded again")

    export = commands.add_parser("export-vectors", help="write a snapshot's vectors, for another build to take")
    export.add_argument("--snapshot", default=snapshot_id())
    export.add_argument("--to", required=True)
    export.add_argument("--chunk-table", default="", help="instead of the snapshot's")
    export.add_argument("--embed-table", default="", help="instead of the snapshot's")

    tables = commands.add_parser("tables", help="print the settings that point the provider at a snapshot's tables")
    tables.add_argument("--snapshot", required=True)

    activate = commands.add_parser("activate", help="swap a snapshot over the live names")
    activate.add_argument("--snapshot", default=snapshot_id())
    activate.add_argument("--allow-shrink", action="store_true")

    commands.add_parser("versions", help="list the builds recorded")
    commands.add_parser("fingerprint", help="print the source fingerprint")
    commands.add_parser("current", help="exit 0 when the live build already matches the source")

    restore = commands.add_parser("restore", help="restore a pg_dump into the index database")
    restore.add_argument("--url", required=True)
    restore.add_argument("--file", default="/tmp/regulation.dump")

    args = parser.parse_args(argv)
    if args.command == "build":
        return _build(args)
    if args.command == "export-vectors":
        return _export_vectors(args)
    if args.command == "tables":
        return _tables(args)
    if args.command == "activate":
        return _activate(args)
    if args.command == "versions":
        return _versions()
    if args.command == "fingerprint":
        print(builder.source_fingerprint())
        return 0
    if args.command == "current":
        return _current()
    if args.command == "restore":
        return _restore(args)
    return 2


def _build(args: argparse.Namespace) -> int:
    tables = Tables.for_snapshot(args.snapshot)
    count = builder.build(args.snapshot, tables, limit=args.limit or None)
    builder.build_metadata(tables)
    builder.build_links(tables)
    if not args.skip_embed:
        model = load_model(args.model)
        with psycopg.connect(index_url()) as conn:
            create_table(conn, table_name(tables.embeddings), MODELS[args.model]["dim"])
            conn.commit()
            reuse_live_vectors(conn, tables, args.model)
            if args.vectors:
                with open_vectors(args.vectors) as source:
                    taken = import_vectors(conn, tables.chunks, tables.embeddings, source, MODELS[args.model]["dim"])
                print(f"vectors taken from {args.vectors.split('?')[0]}: {taken:,}", flush=True)
            embed(conn, tables.chunks, tables.embeddings, model)
            index_vectors(conn, table_name(tables.embeddings), MODELS[args.model]["dim"])
            conn.commit()
    problems = builder.validate(tables, require_vectors=not args.skip_embed)
    if problems:
        for problem in problems:
            print(f"build: {problem}", file=sys.stderr)
        return 1
    builder.record(args.snapshot, tables, "ready", args.model)
    print(json.dumps({"snapshot": args.snapshot, "chunks": count, "tables": tables.__dict__}))
    return 0


def reuse_live_vectors(conn: psycopg.Connection, tables: Tables, model: str) -> None:
    """Take the live build's vectors where they are this model's: only new or changed chunks are embedded."""
    live = builder.live_vectors(LIVE)
    if live is None:
        return
    source, live_model = live
    if live_model != model:
        print(f"the live build's vectors are {live_model}'s, not {model}'s: none taken", flush=True)
        return
    taken = seed_vectors(conn, tables.chunks, tables.embeddings, source)
    print(f"vectors taken from the live build: {taken:,}", flush=True)


def _export_vectors(args: argparse.Namespace) -> int:
    tables = Tables.for_snapshot(args.snapshot)
    chunks = table_name(args.chunk_table or tables.chunks)
    embeddings = table_name(args.embed_table or tables.embeddings)
    with psycopg.connect(index_url()) as conn, open(args.to, "wb") as out:
        written = export_vectors(conn, chunks, embeddings, out)
    print(f"{written:,} vectors to {args.to}")
    return 0


def _tables(args: argparse.Namespace) -> int:
    """Settings for the provider (wiring.py) to read this snapshot's tables, one NAME=value per line."""
    tables = Tables.for_snapshot(args.snapshot)
    print(f"{CHUNK_TABLE}={tables.chunks}\n{EMBED_TABLE}={tables.embeddings}\n{META_TABLE}={tables.meta}")
    print(f"{INDEX_VERSION}=regulation-{args.snapshot}")
    return 0


def _activate(args: argparse.Namespace) -> int:
    tables = Tables.for_snapshot(args.snapshot)
    problems = builder.validate(tables, require_vectors=True)
    if problems:
        for problem in problems:
            print(f"activate: {problem}", file=sys.stderr)
        return 1
    builder.activate(tables, LIVE, allow_shrink=args.allow_shrink)
    builder.record(args.snapshot, LIVE, "live", builder.snapshot_model(args.snapshot))
    print(f"activated {args.snapshot}")
    return 0


def _current() -> int:
    """Has the platform published anything since the live build?"""
    source = builder.source_fingerprint()
    with psycopg.connect(index_url()) as conn:
        table = conn.execute("select to_regclass('regulation_build')").fetchone()[0]
        if not table:
            print(f"source {source}; no build recorded")
            return 1
        row = conn.execute(
            "select source_fingerprint from regulation_build where status = 'live' "
            "and source_fingerprint is not null order by built_at desc limit 1"
        ).fetchone()
    if row and row[0] == source:
        print(f"unchanged: {source}")
        return 0
    print(f"changed: {source} (live: {row[0] if row else 'none'})")
    return 1


def _versions() -> int:
    with psycopg.connect(index_url()) as conn:
        rows = conn.execute(
            "select snapshot_id, status, chunk_count, vector_count, source_fingerprint, built_at "
            "from regulation_build order by built_at desc limit 20"
        ).fetchall()
    for row in rows:
        print("  ".join(str(value) for value in row))
    return 0


def _restore(args: argparse.Namespace) -> int:
    import subprocess
    import urllib.request

    with urllib.request.urlopen(args.url, timeout=120) as response, open(args.file, "wb") as out:
        while True:
            block = response.read(4 << 20)
            if not block:
                break
            out.write(block)
    print(f"downloaded to {args.file}")
    return subprocess.run(
        ["pg_restore", "--no-owner", "--no-privileges", "--clean", "--if-exists", "--dbname", index_url(), args.file],
        check=False,
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
