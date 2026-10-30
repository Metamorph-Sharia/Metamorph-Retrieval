"""What the stand-in needs from published, in batches: a describe of forty refs is two queries, not forty."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from metamorph_regulation_standin.domain.records import Document, Unit


class RegulationReadModel(Protocol):
    def published_at(self) -> datetime | None:
        """The newest document's publish."""
        ...

    def documents(self, ids: Sequence[str]) -> list[Document]:
        """Those published, in any order."""
        ...

    def units(self, keys: Sequence[tuple[str, str]]) -> list[Unit]:
        """The provision units under these (document id, address) pairs that are published, in any order."""
        ...
