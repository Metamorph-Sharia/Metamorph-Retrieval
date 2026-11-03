"""Several providers' rankings as one: reciprocal rank fusion, and the gateway's cursor over a ranking it made.

A provider's score is comparable only within its own call (the contract), so fusion uses ranks alone: each hit scores
1 / (k + rank) in each ranking it appears in. Equal scores keep the providers' order, then their ranks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from metamorph_retrieval_contract.errors import InvalidArgument
from metamorph_retrieval_contract.evidence import EmptyReason, Hit, Page

RRF_K = 60  # the usual constant: a hit's rank matters, a few places more or less matter little
CURSOR = "fused:"


def fused_page(pages: Sequence[Page[Hit]], *, start: int, limit: int, warnings: tuple[str, ...],
               why_empty: EmptyReason) -> Page[Hit]:
    """The fused ranking from `start`, `limit` hits long, ranked anew from 1 and scored by fusion."""
    return ranked_page(fuse(pages), start=start, limit=limit, warnings=warnings, why_empty=why_empty)


def ranked_page(ranked: Sequence[tuple[Hit, float]], *, start: int, limit: int, warnings: tuple[str, ...],
                why_empty: EmptyReason) -> Page[Hit]:
    """A ranking the gateway made, from `start`, `limit` hits long, ranked anew from 1, with its scores."""
    chosen = ranked[start:start + limit]
    if not chosen:
        return Page.empty(why_empty if not ranked else EmptyReason.NO_MATCH, warnings)
    following = start + limit
    return Page(tuple(replace(hit, rank=rank, score=score)
                      for rank, (hit, score) in enumerate(chosen, start=start + 1)),
                cursor=f"{CURSOR}{following}" if following < len(ranked) else None, warnings=warnings)


def fuse(pages: Sequence[Page[Hit]], k: int = RRF_K) -> list[tuple[Hit, float]]:
    scores: dict[str, float] = {}
    first: dict[str, tuple[Hit, int, int]] = {}  # each ref's hit, from the first ranking holding it
    for order, page in enumerate(pages):
        for hit in page.items:
            key = str(hit.evidence.ref)
            scores[key] = scores.get(key, 0.0) + 1 / (k + hit.rank)
            first.setdefault(key, (hit, hit.rank, order))
    best = sorted(scores, key=lambda key: (-scores[key], first[key][1], first[key][2]))
    return [(first[key][0], scores[key]) for key in best]


def offset_of(cursor: str | None) -> int:
    if cursor is None:
        return 0
    offset = cursor.removeprefix(CURSOR)
    if not cursor.startswith(CURSOR) or not offset.isdigit():
        raise InvalidArgument(f"cursor {cursor!r} is not one this search gave; leave it out for the first page")
    return int(offset)
