"""What a search may be narrowed to, in the index's own terms.

The store applies these while it looks for candidates, not afterwards: a filter
applied to a page that was already cut to `limit` can empty a page that had
matches further down.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Filters:
    kinds: frozenset[str] = frozenset()  # empty: every kind
    issuers: frozenset[str] = frozenset()
    documents: tuple[str, ...] = ()  # document ids
    in_force_on: date | None = None  # the documents in force that day, and their provisions not yet ended

    def __bool__(self) -> bool:
        return bool(self.kinds or self.issuers or self.documents or self.in_force_on)


NO_FILTERS = Filters()
