"""A provision's own status, read from the document's address-level events.

A document that was partly revoked borrows that status for every one of its
provisions, so an agent warns readers about articles nothing ever touched.
The platform publishes status events per address (`published.status_event`), and
this module decides what a single provision's status really is.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from datetime import date

IN_FORCE = "in_force"
AMENDED = "amended"
REVOKED = "revoked"
PARTLY_REVOKED = "partly_revoked"
UNKNOWN = "unknown"
NOT_YET_IN_FORCE = "not_yet_in_force"

# A provision can't be more in force than its document, and `unknown` says we
# know nothing more than the document does.
DOCUMENT_WINS = frozenset({REVOKED, NOT_YET_IN_FORCE, UNKNOWN})

PENJELASAN = "penjelasan"


def provision_status(address: str, document_status: str, events: Mapping[str, str]) -> str:
    """Status of one provision, given its document's status and its events.

    `events` maps an address of this document to the status of its latest
    address-level event; the caller picks the latest, this only reads the map.
    """
    if document_status in DOCUMENT_WINS:
        return document_status

    explained = _explained_address(address)
    if explained:
        for holder in _holders(explained):
            if holder in events:
                return events[holder]
        inside = [status for held, status in events.items() if held.startswith(explained + "/")]
        if inside:
            return PARTLY_REVOKED if REVOKED in inside else AMENDED

    if events:
        # The data covers this document's changes, and none of them touch here.
        return IN_FORCE
    return document_status


def latest_events(rows: Iterable[tuple[str, str, date | None]]) -> dict[str, str]:
    """Per address, the status of its latest event; an undated event came early."""
    latest: dict[str, tuple[date | None, str]] = {}
    for address, status, effective_from in rows:
        held = latest.get(address)
        if held is None or _is_later(effective_from, held[0]):
            latest[address] = (effective_from, status)
    return {address: status for address, (_, status) in latest.items()}


def _is_later(new: date | None, old: date | None) -> bool:
    if new is None:
        return old is None
    if old is None:
        return True
    return new >= old


def _explained_address(address: str) -> str:
    """The address of the provision an elucidation explains; "" for elucidation itself."""
    address = (address or "").strip().strip("/")
    if address == PENJELASAN:
        return ""
    if address.startswith(PENJELASAN + "/"):
        return address[len(PENJELASAN) + 1 :]
    return address


def _holders(address: str) -> Iterator[str]:
    """The address itself, then each address holding it, nearest first."""
    parts = address.split("/")
    for size in range(len(parts), 0, -1):
        yield "/".join(parts[:size])
