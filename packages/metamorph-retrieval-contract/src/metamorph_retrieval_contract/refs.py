"""Refs: the stable keys evidence is cited, cached and followed by.

A ref is `{namespace}:{id}[#{address}]`, e.g. `doc:ojk:pojk:2024:40#pasal-5/ayat-1` or `report:ojk:lpksi:2025#p-12`.
Each namespace belongs to one provider, which declares it in its manifest. The id and the address come from the
platform's read contracts, never from an index, so a ref survives a re-index or a new embedding model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from metamorph_retrieval_contract.errors import InvalidArgument

NAMESPACE = re.compile(r"[a-z][a-z0-9_]*")
REF = re.compile(r"(?P<namespace>[a-z][a-z0-9_]*):(?P<id>[^\s#]+)(?:#(?P<address>[^\s#]+))?")
EXAMPLE = "doc:ojk:pojk:2024:40#pasal-5"


@dataclass(frozen=True)
class Ref:
    namespace: str
    id: str
    address: str | None = None  # a part of the whole: a provision, a passage

    def __post_init__(self) -> None:
        if not REF.fullmatch(str(self)):
            raise InvalidArgument(f"{str(self)!r} is not a ref, such as {EXAMPLE}")

    @classmethod
    def parse(cls, text: str) -> Ref:
        match = REF.fullmatch(text)
        if not match:
            raise InvalidArgument(f"{text!r} is not a ref, such as {EXAMPLE}")
        return cls(match["namespace"], match["id"], match["address"])

    def whole(self) -> Ref:
        return Ref(self.namespace, self.id)

    def holds(self, other: Ref) -> bool:
        """Whether `other` is this ref or a part of it: a document holds its articles, an article its paragraphs."""
        if self.whole() != other.whole():
            return False
        if self.address is None or other.address == self.address:
            return True
        return other.address is not None and other.address.startswith(f"{self.address}/")

    def overlaps(self, other: Ref) -> bool:
        return self.holds(other) or other.holds(self)

    def __str__(self) -> str:
        return f"{self.namespace}:{self.id}" + (f"#{self.address}" if self.address is not None else "")
