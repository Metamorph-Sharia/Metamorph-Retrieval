"""The read model over the platform's published schema: documents, and provision_unit (the read contract's view of
what to cite and embed). Read only; nothing here writes."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from metamorph_regulation_standin.domain.records import Document, Unit

DOCUMENT = """d.id, d.issuer, d.family, d.number, d.year, d.citation, d.title, d.kind, d.status, d.status_as_of,
              d.enacted_on, d.promulgated_on, d.effective_on, d.aliases, d.published_at"""


class PostgresRegulationReadModel:
    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def published_at(self) -> datetime | None:
        return self.connection.execute("SELECT max(published_at) FROM published.document").fetchone()[0]

    def documents(self, ids: Sequence[str]) -> list[Document]:
        if not ids:
            return []
        rows = self._rows(f"SELECT {DOCUMENT} FROM published.document d WHERE d.id = ANY(%(ids)s)",
                          {"ids": list(ids)})
        return [_document(row) for row in rows]

    def units(self, keys: Sequence[tuple[str, str]]) -> list[Unit]:
        if not keys:
            return []
        rows = self._rows(f"""
            SELECT {DOCUMENT}, u.address, u.heading_path, u.wording, u.page_start, u.page_end, u.valid_from,
                   u.valid_to, u.under_review
            FROM published.provision_unit u JOIN published.document d ON d.id = u.document_id
            WHERE (u.document_id, u.address) IN (SELECT * FROM unnest(%(ids)s::text[], %(addresses)s::text[]))""",
                          {"ids": [id_ for id_, _ in keys], "addresses": [address for _, address in keys]})
        return [Unit(document=_document(row), address=row["address"], heading_path=tuple(row["heading_path"]),
                     wording=row["wording"], page_start=row["page_start"], page_end=row["page_end"],
                     valid_from=row["valid_from"], valid_to=row["valid_to"], under_review=row["under_review"])
                for row in rows]

    def _rows(self, query: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            return cursor.execute(query, parameters).fetchall()  # type: ignore[arg-type]


def _document(row: dict[str, Any]) -> Document:
    return Document(id=row["id"], issuer=row["issuer"], family=row["family"], number=row["number"], year=row["year"],
                    citation=row["citation"], title=row["title"], kind=row["kind"], status=row["status"],
                    status_as_of=row["status_as_of"], enacted_on=row["enacted_on"],
                    promulgated_on=row["promulgated_on"], effective_on=row["effective_on"],
                    aliases=tuple(row["aliases"]), published_at=row["published_at"])
