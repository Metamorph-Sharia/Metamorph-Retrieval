"""Pages of a tool's results. A cursor is the offset of the next page: the order is fixed, so it stays valid."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from metamorph_retrieval_contract.errors import InvalidArgument
from metamorph_retrieval_contract.evidence import EmptyReason, Page

Item = TypeVar("Item")


def offset_of(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isdigit():
        raise InvalidArgument(f"cursor {cursor!r} is not one this tool gave; leave it out for the first page")
    return int(cursor)


def paged(items: Sequence[Item], limit: int, cursor: str | None, empty_reason: EmptyReason) -> Page[Item]:
    start = offset_of(cursor)
    chosen = tuple(items[start : start + limit])
    if not chosen:
        return Page.empty(empty_reason)
    following = start + limit
    return Page(chosen, cursor=str(following) if following < len(items) else None)
