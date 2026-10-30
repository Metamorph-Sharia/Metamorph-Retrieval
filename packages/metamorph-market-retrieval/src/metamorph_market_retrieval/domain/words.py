"""Words, for matching a query to a name by what they share. Exact words only: meaning comes with search (M4)."""

from __future__ import annotations

import re
from collections.abc import Sequence

WORD = re.compile(r"\w+")


def words(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(WORD.findall(text.casefold())))


def word_score(query_words: Sequence[str], text: str) -> float:
    """The share of the query's words the text holds: 1 when it holds them all."""
    if not query_words:
        return 0.0
    held = set(words(text))
    return sum(1 for word in query_words if word in held) / len(query_words)


def word_precision(query_words: Sequence[str], text: str) -> float:
    """The share of the text's words the query holds: 1 when the text says nothing else. Between texts holding all
    the query's words, the one naming exactly what was asked, not one of its parts."""
    held = words(text)
    if not held:
        return 0.0
    asked = set(query_words)
    return sum(1 for word in held if word in asked) / len(held)
