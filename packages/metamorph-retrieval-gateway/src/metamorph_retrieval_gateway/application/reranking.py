"""Reranking: a model that reads the question with each candidate and scores them all on one scale.

Fusion knows only ranks, and a rank says nothing across providers: the first market passage and the first regulation
are equal to it. A reranker reads each candidate against the question, so its order holds across providers. It is a
port: the gateway's application knows no model, and the wiring chooses one, or none.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, Protocol

from metamorph_retrieval_contract.evidence import Evidence, Hit, Record, Strength, Text

CANDIDATES = 50  # fused candidates reranked: enough to lift one from far down, few enough to be fast
TIMEOUT = 10.0  # seconds the reranker has, past which the fused order stands: 50 candidates on 2 vCPUs need more than 5
NOT_RERANKED = "results in fused order: the reranker didn't answer in time"
RERANK = "rerank"  # its stage in a call

# This reranker's raw logits, measured on the local index with cross-encoder/mmarco-mMiniLMv2-L12-H384-v1: of 136
# eval queries the corpus answers, no best hit scored under -2.45 (of the 104 expected ones, -2.92), while ten
# off-topic ones ("resep rendang", "who won the 2022 world cup") best scored -4.2 to -8.3; under 0 went 5 of the 136.
# Another reranker scores on another scale: set both again on the eval.
FLOOR = -4.0  # below it, a candidate is about nothing asked: dropped
WEAK = 0.0  # below it, a hit probably isn't about the question
NOTHING_RELEVANT = "nothing scored as relevant: rephrase the question, or conclude the sources hold nothing on it"


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


def judged(ranked: Sequence[tuple[Hit, float]]) -> list[tuple[Hit, float]]:
    """The reranked candidates worth showing, each with its strength; those under the floor are left out."""
    return [(replace(hit, strength=Strength.WEAK if score < WEAK else Strength.STRONG), score)
            for hit, score in ranked if score >= FLOOR]


def _plain(fields: Mapping[str, Any]) -> list[tuple[str, Any]]:
    return [(name, value) for name, value in fields.items() if isinstance(value, str | int | float) and value != ""]
