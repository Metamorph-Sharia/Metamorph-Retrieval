"""A document's outline: its units in reading order, grouped under the headings above them.

An agent reads a document's ref, then browses to the article it needs. The rule comes from the parser's structure, not
from a per-document table: bab, bagian and paragraf are headings; the units are the provisions directly under the
document or under a heading, so an ayat or huruf inside an article is not a unit of the outline.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

HEADING_KINDS = frozenset({"bab", "bagian", "paragraf"})


@dataclass(frozen=True)
class OutlineProvision:
    address: str
    kind: str
    parent_address: str | None
    ordinal: int
    depth: int
    heading_path: Sequence[str]
    title: str | None = None  # the unit's own heading, as a romawi or a diktum has: "KETENTUAN UMUM"


def document_outline(provisions: Iterable[OutlineProvision]) -> list[dict[str, Any]]:
    """The units by ordinal, consecutive units sharing the same headings in one group, with the titles units have."""
    rows = list(provisions)
    headings = {row.address for row in rows if row.kind in HEADING_KINDS}
    units = sorted(
        (row for row in rows
         if row.kind not in HEADING_KINDS
         and (row.parent_address is None or row.parent_address in headings)),
        key=lambda row: row.ordinal,
    )
    groups: list[dict[str, Any]] = []
    for unit in units:
        # The path runs from the document down to the unit itself, so the entry at its depth is the unit's own and
        # everything above it is a heading.
        heading = " > ".join(unit.heading_path[:unit.depth]) or None
        if not groups or groups[-1]["heading"] != heading:
            groups.append({"heading": heading, "units": []})
        groups[-1]["units"].append(unit.address)
        title = (unit.title or "").strip(" :")
        if title:
            groups[-1].setdefault("titles", {})[unit.address] = title
    return groups
