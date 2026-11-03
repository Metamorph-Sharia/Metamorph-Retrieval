"""Refs: the stable key an agent cites, caches and passes back to us.

The shape is the platform's retrieval contract:

    doc:{document_id}#{address}
    doc:ojk:pojk:2024:40#pasal-137/ayat-3

Both halves already exist in our index (`document_id`, `address`), so a ref is a
formatting rule, not a new identifier. That is what lets this surface join a
gateway later without re-indexing.
"""

from __future__ import annotations

from dataclasses import dataclass

NAMESPACE = "doc"
EXAMPLE = "doc:ojk:pojk:2024:40#pasal-5"


class RefError(ValueError):
    """The caller's ref is malformed, or not one we own."""


@dataclass(frozen=True)
class Ref:
    document_id: str
    address: str | None = None

    def __str__(self) -> str:
        suffix = f"#{self.address}" if self.address else ""
        return f"{NAMESPACE}:{self.document_id}{suffix}"


def make_ref(document_id: str, address: str | None = None) -> str:
    if not document_id or "#" in document_id or " " in document_id:
        raise RefError(f"{document_id!r} is not a document id")
    return str(Ref(document_id, address or None))


def parse_ref(text: str) -> Ref:
    value = (text or "").strip()
    prefix, separator, rest = value.partition(":")
    if prefix != NAMESPACE or not separator or not rest:
        raise RefError(f"{text!r} is not a ref, such as {EXAMPLE}")
    document_id, _, address = rest.partition("#")
    if not document_id:
        raise RefError(f"{text!r} names no document")
    return Ref(document_id, address or None)
