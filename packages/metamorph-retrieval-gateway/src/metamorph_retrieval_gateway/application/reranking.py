"""Reranking: a model that reads the question with each candidate and scores them all on one scale.

Fusion knows only ranks, and a rank says nothing across providers: the first market passage and the first regulation
are equal to it. A reranker reads each candidate against the question, so its order holds across providers. It is a
port: the gateway's application knows no model, and the wiring chooses one, or none.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from metamorph_retrieval_contract.evidence import Evidence, Record, Text

CANDIDATES = 50  # fused candidates reranked: enough to lift one from far down, few enough to be fast
TIMEOUT = 5.0  # seconds the reranker has; past them, the fused order stands
NOT_RERANKED = "results in fused order: the reranker didn't answer in time"


class Reranker(Protocol):
    def scores(self, query: str, texts: Sequence[str]) -> Sequence[float]:
        """One relevance score per text, for the question: the higher, the more relevant."""
        ...


def rerank_text(evidence: Evidence) -> str:
    """What the reranker reads of a candidate: what a reader sees first, its citation, its title, then its words or
    the record's plain fields. The model reads only so far, so the most telling comes first."""
    lines = [evidence.citation, evidence.title]
    if isinstance(evidence.body, Text):
        lines.append(evidence.body.wording)
    elif isinstance(evidence.body, Record):
        lines.extend(f"{name}: {value}" for name, value in _plain(evidence.body.fields))
    return "\n".join(line for line in lines if line)


def _plain(fields: Mapping[str, Any]) -> list[tuple[str, Any]]:
    return [(name, value) for name, value in fields.items() if isinstance(value, str | int | float) and value != ""]
