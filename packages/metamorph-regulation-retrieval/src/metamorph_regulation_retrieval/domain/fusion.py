"""Reciprocal rank fusion: rankings joined by rank, not score, since scores from full text and from vectors aren't
comparable. A unit ranked high by both beats one ranked first by only one. (The market provider fuses its two rankings
the same way; providers share only the contract, so each keeps its own copy of these few lines.)"""

from __future__ import annotations

from collections.abc import Sequence

RRF_K = 60  # dampens the top ranks' weight; the value the method's authors found robust


def reciprocal_rank_fusion(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Every key with its fused score, best first; equal scores by key, so the same call gives the same order."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
