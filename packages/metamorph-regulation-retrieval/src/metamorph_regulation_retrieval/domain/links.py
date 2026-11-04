"""A regulation's links: what changes it, what it carries out, what it rests on and what it cites.

The platform states them (`published.edge`); here they are what a link means to whoever asks about a regulation. What
changes a text comes first, since it decides whether the text is still the rule; a citation comes last, since most
regulations have many. A change to a document or an article changes every provision inside it, so it is a link of
those too (the store). A citation of the whole document says nothing of any one provision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

CHANGING = ("revokes", "partly_revokes", "supersedes", "amends", "changes_fatwa")
ORDER = (*CHANGING, "implements", "adopts_fatwa", "legal_basis", "refers_to")

# The platform says how a link was found: high, as a source states it; medium, by pattern in the text. A link's
# confidence in the contract is a number.
CONFIDENCE = {"high": 0.9, "medium": 0.6, "low": 0.3}


@dataclass(frozen=True)
class LinkRow:
    type: str
    from_document: str
    from_address: str | None
    to_document: str
    to_address: str | None
    effective_on: date | None
    confidence: str | None
