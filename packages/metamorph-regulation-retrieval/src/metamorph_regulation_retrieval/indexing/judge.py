"""Judge a freshly built index against the one that is answering, before the swap.

Two numbers, measured the same way for both arms:

- **document@5** — is the right document among the first five distinct documents?
- **clause in set** — is the expected provision among the returned passages?

The cases are metamorph-eval's (eval/regulation/cases.jsonl), so the judge and
`metamorph-eval run` read one question set: each `search_documents` case's query,
and its expected refs, `doc:{document_id}#{address}`. A ref without an address is
document-level evidence; an address may name a parent, to match its children.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

from ..domain.refs import parse_ref
from .config import index_url

SEARCH = """
select c.document_id, c.address
from {embed} e join {chunk} c using (chunk_id)
where c.searchable
order by e.embedding <=> %s::vector
limit %s
"""


@dataclass(frozen=True)
class Score:
    documents_at_5: float
    clause_in_set: float
    evidence: int


def load_cases(path: Path) -> list[dict]:
    """The search cases, as the judge measures them: a question and the provisions it expects."""
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [
        {"question": case["arguments"]["query"], "expected": [_expected(ref) for ref in case["expect"].get("refs", ())]}
        for case in cases
        if case.get("tool") == "search_documents"
    ]


def _expected(text: str) -> dict:
    ref = parse_ref(text)
    return {"document_id": ref.document_id, "address": ref.address}


def measure(
    cases: list[dict],
    chunk_table: str,
    embed_table: str,
    vectors: dict[str, list[float]],
    *,
    limit: int = 50,
) -> Score:
    documents = clauses = total = 0
    with psycopg.connect(index_url()) as conn:
        register_vector(conn)
        conn.execute(f"set local hnsw.ef_search = {max(limit, 40)}")
        for case in cases:
            rows = conn.execute(
                SEARCH.format(chunk=chunk_table, embed=embed_table),
                (vectors[case["question"]], limit),
            ).fetchall()
            top = list(dict.fromkeys(document_id for document_id, _ in rows))[:5]
            for expected in case.get("expected", []):
                total += 1
                documents += int(expected["document_id"] in top)
                clauses += int(_found(expected, top, rows))
    return Score(
        documents_at_5=round(documents / max(1, total), 4),
        clause_in_set=round(clauses / max(1, total), 4),
        evidence=total,
    )


def _found(expected: dict, top: list[str], rows: list[tuple[str, str]]) -> bool:
    document = expected["document_id"]
    if document not in top:
        return False
    address = expected.get("address")
    if not address:
        return True
    return any(
        candidate == document and (candidate_address == address or candidate_address.startswith(address + "/"))
        for candidate, candidate_address in rows
    )


def worse_than(new: Score, active: Score, tolerance: float) -> list[str]:
    worse = []
    if new.documents_at_5 < active.documents_at_5 - tolerance:
        worse.append("document@5")
    if new.clause_in_set < active.clause_in_set - tolerance:
        worse.append("clause in set")
    return worse
