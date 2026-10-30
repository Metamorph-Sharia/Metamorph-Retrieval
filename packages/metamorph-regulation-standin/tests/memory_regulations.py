"""The read model in memory: the samples, as the stand-in would find them in published."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from standin_samples import ARTICLE_5_1, FATWA_117, POJK_40, RULING

from metamorph_regulation_standin.domain.records import Document, Unit


class MemoryRegulations:
    def __init__(self, documents: Sequence[Document] = (POJK_40, FATWA_117),
                 units: Sequence[Unit] = (ARTICLE_5_1, RULING)) -> None:
        self.all_documents = {document.id: document for document in documents}
        self.all_units = {(unit.document.id, unit.address): unit for unit in units}

    def published_at(self) -> datetime | None:
        return max((document.published_at for document in self.all_documents.values()), default=None)

    def documents(self, ids: Sequence[str]) -> list[Document]:
        return [self.all_documents[id_] for id_ in dict.fromkeys(ids) if id_ in self.all_documents]

    def units(self, keys: Sequence[tuple[str, str]]) -> list[Unit]:
        return [self.all_units[key] for key in dict.fromkeys(keys) if key in self.all_units]
