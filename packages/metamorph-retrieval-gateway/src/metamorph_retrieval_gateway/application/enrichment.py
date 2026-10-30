"""Citing what a record names. A provider names other refs by `{"ref": …}` stubs in its records' fields, e.g. the
regulations governing an industry. For the refs another provider owns, the gateway asks that owner for their cards,
in one batch, and adds to each stub what an agent weighs it by: kind, citation, title, legal force and status. What a
stub already says is kept. A provider's own refs are left as it named them: it could have cited them itself.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from metamorph_retrieval_contract.evidence import Evidence
from metamorph_retrieval_contract.provider import JSON
from metamorph_retrieval_contract.refs import REF, Ref

MAX_NAMED = 40  # refs cited in one answer; the rest stay bare, and the answer says how many


def named(value: Any) -> Iterator[Ref]:
    """Every ref a stub holds, however deep in the fields."""
    if isinstance(value, Mapping):
        if isinstance(value.get("ref"), str) and REF.fullmatch(value["ref"]):  # not a ref: nobody's to cite
            yield Ref.parse(value["ref"])
        for inner in value.values():
            yield from named(inner)
    elif isinstance(value, list | tuple):
        for inner in value:
            yield from named(inner)


def cited(value: Any, cards: Mapping[str, JSON]) -> Any:
    """The fields, with each stub whose ref has a card given what the card says and the stub doesn't."""
    if isinstance(value, Mapping):
        fields = {key: cited(inner, cards) for key, inner in value.items()}
        card = cards.get(value["ref"]) if isinstance(value.get("ref"), str) else None
        return {"ref": value["ref"], **card, **fields} if card else fields
    if isinstance(value, list | tuple):
        return [cited(inner, cards) for inner in value]
    return value


def card_fields(card: Evidence) -> JSON:
    fields = {"kind": card.kind, "citation": card.citation, "title": card.title,
              "legal_force": card.legal_force.value}
    return fields | ({"status": card.qualifiers.status} if card.qualifiers.status else {})


def past_budget(count: int) -> str:
    return (f"{count} named refs left without citations, past the {MAX_NAMED} cited in one answer; read them for "
            "theirs")
