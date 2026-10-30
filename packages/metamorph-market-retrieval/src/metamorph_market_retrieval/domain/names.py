"""Finding a company by a name: its legal name or any other it was listed under, a platform's name included.

Names are matched, never merged: joining records into one company is the platform's (the system of record). A name
that fits several companies returns them all, best first, each saying how it matched, for the agent to choose.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum

LEGAL_FORMS = frozenset({"pt", "tbk", "persero", "perseroda"})  # Indonesian company forms, dropped when comparing
NOT_A_WORD = re.compile(r"[^\w]+")
FUZZY_AT_LEAST = 0.85  # a misspelling: "Investre Radika" for "Investree Radhika" scores 0.95, unrelated names < 0.5


class NameMatch(StrEnum):
    EXACT = "exact"  # as listed, ignoring case
    NORMALISED = "normalised"  # ignoring punctuation and legal form too
    PARTIAL = "partial"  # every word asked is in the name
    FUZZY = "fuzzy"  # close to the name, as a misspelling is


@dataclass(frozen=True)
class Match:
    kind: NameMatch
    score: float  # 1 for exact; a partial match scores more the more of the name it covers; fuzzy at most 0.5


def normalised(name: str) -> str:
    words = NOT_A_WORD.sub(" ", unicodedata.normalize("NFKC", name).casefold()).split()
    return " ".join(word for word in words if word not in LEGAL_FORMS)


def name_match(query: str, names: Iterable[str]) -> Match | None:
    matches = [match for name in names if (match := _match(query, name))]
    return max(matches, key=lambda match: match.score, default=None)


def rank_by_name(query: str, candidates: Mapping[str, Iterable[str]]) -> list[tuple[str, Match]]:
    """Every candidate one of whose names matches, best first; ties by key, so the order is the same every time."""
    found = [(key, match) for key, names in candidates.items() if (match := name_match(query, names))]
    return sorted(found, key=lambda pair: (-pair[1].score, pair[0]))


def _match(query: str, name: str) -> Match | None:
    if query.casefold().strip() == name.casefold().strip():
        return Match(NameMatch.EXACT, 1.0)
    asked, listed = normalised(query), normalised(name)
    if not asked:
        return None
    if asked == listed:
        return Match(NameMatch.NORMALISED, 0.95)
    asked_words, listed_words = asked.split(), listed.split()
    if set(asked_words) <= set(listed_words):
        return Match(NameMatch.PARTIAL, 0.5 + 0.4 * len(asked_words) / len(listed_words))
    ratio = SequenceMatcher(None, asked, listed).ratio()
    return Match(NameMatch.FUZZY, 0.5 * ratio) if ratio >= FUZZY_AT_LEAST else None
