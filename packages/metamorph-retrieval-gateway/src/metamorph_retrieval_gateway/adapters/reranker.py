"""A cross-encoder reranker, run in the gateway's process: no call leaves it, and nothing is paid per question.

The model reads the question and a candidate together, up to MAX_TOKENS of them: a candidate's citation, title and
first words (reranking.rerank_text), which is where the gateway puts what tells most. It loads when the gateway starts,
so the first question doesn't wait for it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

MAX_TOKENS = 256  # measured (eval/regulation, 2026-11-03): as good as 512 on the question sets, and half the time
BATCH = 16


class CrossEncoderReranker:
    def __init__(self, model: str, *, max_tokens: int = MAX_TOKENS, encoder: Any = None) -> None:
        self.model = model
        self.encoder = encoder or _load(model, max_tokens)

    def scores(self, query: str, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []
        scores = self.encoder.predict([(query, text) for text in texts], batch_size=BATCH, show_progress_bar=False)
        return [float(score) for score in scores]


def _load(model: str, max_tokens: int) -> Any:
    from sentence_transformers import CrossEncoder  # the `rerank` extra

    return CrossEncoder(model, max_length=max_tokens)
