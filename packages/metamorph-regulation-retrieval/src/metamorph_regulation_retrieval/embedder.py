"""Embed the question, in the same process that answers it.

bge-m3 at 512 tokens, normalised, no prefix - the settings the index was built
with. The model is loaded once and reused; the gateway already loads it for the
market provider.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Protocol

MODEL = "BAAI/bge-m3"
DIMENSION = 1024
MAX_SEQ_LEN = 512
DEVICE = "METAMORPH_REGULATION_DEVICE"


class Embedder(Protocol):
    def encode(self, text: str) -> Sequence[float]: ...


class SentenceTransformerEmbedder:
    """Lazy: the model loads on the first question, not at import."""

    def __init__(self, model_id: str = MODEL, max_seq_len: int = MAX_SEQ_LEN) -> None:
        self.model_id = model_id
        self.max_seq_len = max_seq_len
        self._model = None

    def encode(self, text: str) -> Sequence[float]:
        if self._model is None:
            self._model = _load(self.model_id, self.max_seq_len)
        vector = self._model.encode([text], normalize_embeddings=True, show_progress_bar=False)
        return vector[0]


def _load(model_id: str, max_seq_len: int):
    try:
        from sentence_transformers import SentenceTransformer
    except ModuleNotFoundError as error:  # pragma: no cover - the extra is optional
        raise RuntimeError("install the embeddings extra to search the index") from error

    model = SentenceTransformer(model_id, device=os.environ.get(DEVICE) or None)
    model.max_seq_length = max_seq_len
    return model
