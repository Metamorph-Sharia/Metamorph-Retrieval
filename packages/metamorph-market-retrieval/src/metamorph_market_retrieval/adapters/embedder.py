"""Embedding with a local sentence-transformers model. A hosted model waits for AWS (§12 of the architecture).

Each model is used as its makers trained it: e5 models read "query: " and "passage: " prefixes, bge-m3 none. Each
has a similarity floor below which a match by meaning is no match: calibrated on the evaluation set and on
questions the market can't answer, since cosine scales differ between models. Queries are cached in process.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

QUERY_CACHE = 1024
BATCH = 32
MAX_TOKENS = 512  # a platform passage is at most 400 words; its header fits too


@dataclass(frozen=True)
class Model:
    name: str
    query_prefix: str = ""
    passage_prefix: str = ""
    min_similarity: float = 0.0


# Floors calibrated on 2026-10-30 (eval/market/runs/2026-10-30-m4.md): bge-m3's off-topic questions reach 0.49, the
# passages the question set expects mostly 0.59 and up, one English dataset question 0.45. e5's similarities crowd
# into 0.74–0.91, off-topic and relevant alike, so no floor separates them; it also ranks worse, and isn't used.
MODELS = {model.name: model for model in (
    Model("BAAI/bge-m3", min_similarity=0.45),
    Model("intfloat/multilingual-e5-base", "query: ", "passage: ", min_similarity=0.0),
)}


class SentenceTransformerEmbedder:
    def __init__(self, model: Model, *, encoder: Any = None) -> None:
        self.settings = model
        self.model = model.name
        self.encoder = encoder or _load(model.name)
        self._query = lru_cache(maxsize=QUERY_CACHE)(self._embed_query)

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._query(text) for text in texts]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode([self.settings.passage_prefix + text for text in texts])

    def _embed_query(self, text: str) -> list[float]:
        return self._encode([self.settings.query_prefix + text])[0]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self.encoder.encode(texts, batch_size=BATCH, normalize_embeddings=True, show_progress_bar=False)
        return [[float(value) for value in vector] for vector in vectors]


def embedder_for(name: str) -> SentenceTransformerEmbedder:
    if name not in MODELS:
        raise ValueError(f"{name}: not a known embedding model; known: {', '.join(sorted(MODELS))}")
    return SentenceTransformerEmbedder(MODELS[name])


def _load(name: str) -> Any:
    from sentence_transformers import SentenceTransformer  # the `embeddings` extra; only a build or a search loads it

    encoder = SentenceTransformer(name)
    encoder.max_seq_length = MAX_TOKENS
    return encoder
