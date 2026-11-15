"""A document's outline: its units in reading order, grouped under the headings above them.

An agent reads a document's ref, then browses to the article it needs. The rule comes from the parser's structure, not
from a per-document table: the units are the provisions directly under the document or under a heading, so an ayat or
huruf inside an article is not a unit of the outline.

A heading is a provision whose text is its children's: bab, bagian and paragraf, and any provision holding a child
whose address doesn't carry its own. A unit is read by its address and everything under it (pasal-9 with
pasal-9/ayat-1), so a provision holding pasal-1 rather than x/pasal-1 can't be read as one: its children are the
units. That is the decision clause of a regulation without chapters (MEMUTUSKAN holding Pasal 1 …, or an amendment's
Pasal I and Pasal II). An amendment's Pasal I stays a unit: what it quotes is under its address (pasal-i/pasal-13).

A unit must also be readable in one call. A provision too long for one is a heading too, and its parts are the units:
a large amendment's Pasal I reads as each article it changes. And a unit must be readable at all: given what the index
holds, a provision it can't read (an elucidation or a decision with no text of its own) is a heading over the parts it
can, and one with no parts is left out. Headings are found from the document down: what sits inside a unit is the
unit's, so nothing under one is looked at.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence, Set
from dataclasses import dataclass
from typing import Any

HEADING_KINDS = frozenset({"bab", "bagian", "paragraf"})
# The longest unit read in one call: the gateway answers at most 100,000 bytes, and a unit's answer carries more than
# its text.
MOST_UNIT_CHARS = 60_000


@dataclass(frozen=True)
class OutlineProvision:
    address: str
    kind: str
    parent_address: str | None
    ordinal: int
    depth: int
    heading_path: Sequence[str]
    title: str | None = None  # the unit's own heading, as a romawi or a diktum has: "KETENTUAN UMUM"
    length: int = 0  # characters, the provision with everything inside it


def document_outline(provisions: Iterable[OutlineProvision], readable: Set[str] | None = None) -> list[dict[str, Any]]:
    """The units by ordinal, consecutive units sharing the same headings in one group, with the titles units have.
    `readable`: the addresses the index can read; None takes every provision as readable."""
    rows = list(provisions)
    present = {row.address for row in rows}
    children: dict[str | None, list[OutlineProvision]] = defaultdict(list)
    for row in rows:
        children[row.parent_address if row.parent_address in present else None].append(row)

    def is_heading(row: OutlineProvision) -> bool:
        held = children.get(row.address, [])
        return (row.kind in HEADING_KINDS
                or any(not child.address.startswith(row.address + "/") for child in held)
                or (bool(held) and (row.length > MOST_UNIT_CHARS or not can_read(row))))

    def can_read(row: OutlineProvision) -> bool:
        return readable is None or row.address in readable

    found: list[OutlineProvision] = []
    waiting = list(children.get(None, []))
    while waiting:
        row = waiting.pop()
        if is_heading(row):
            waiting.extend(children.get(row.address, []))
        elif can_read(row):
            found.append(row)
    units = sorted(found, key=lambda row: row.ordinal)
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
