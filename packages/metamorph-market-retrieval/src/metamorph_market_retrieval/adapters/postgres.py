"""The read model over PostgreSQL: published_market, read only, through its read contract.

Words are matched with PostgreSQL's full text under the `simple` configuration: exact words, no stemming, over a
dataset's metric, group and industry and a series' label. Filters apply in SQL before ranking, so a filter never
empties a page after the fact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from metamorph_market_retrieval.domain.records import (
    Announcement,
    Company,
    Dataset,
    Industry,
    Licence,
    Listed,
    Mention,
    ObservationRow,
    Passage,
    Register,
    Release,
    Report,
    Sector,
    Series,
)

Row = dict[str, Any]
DATASET_WORDS = "to_tsvector('simple', d.metric || ' ' || d.\"group\" || ' ' || coalesce(d.industry, ''))"
SERIES_WORDS = "to_tsvector('simple', s.label)"
BY_LENGTH = 2  # ts_rank's normalisation: rank / words, so a sub-row repeating its parent's path ranks below it
ADDRESS_NUMBER = "(substring({column} from '[0-9]+'))::int"  # p-2 before p-10


class PostgresMarketReadModel:
    def __init__(self, connection: psycopg.Connection) -> None:
        self.connection = connection

    def published_at(self) -> datetime | None:
        row = self._one("""
            SELECT max(at) AS at FROM (
                SELECT max(published_at) AS at FROM published_market.register
                UNION ALL SELECT max(published_at) FROM published_market.industry
                UNION ALL SELECT max(published_at) FROM published_market.sector) AS published""")
        return row["at"] if row else None

    def companies(self, register: str | None, status: str | None, business_type: str | None) -> list[Company]:
        return self._companies("""
            (%(register)s::text IS NULL OR c.register = %(register)s)
            AND (%(status)s::text IS NULL OR c.status = %(status)s)
            AND (%(business_type)s::text IS NULL OR c.business_type = %(business_type)s)""",
            {"register": register, "status": status, "business_type": business_type})

    def listed_on(self, register: str | None, day: date) -> list[Listed]:
        rows = self._rows("""
            WITH current AS (
                SELECT register, max(edition) AS edition FROM published_market.edition
                WHERE edition <= %(day)s AND (%(register)s::text IS NULL OR register = %(register)s)
                GROUP BY register)
            SELECT e.company_id, current.edition, array_agg(DISTINCT e.kind) AS kinds
            FROM current
            JOIN published_market.listing l ON l.edition = current.edition
            JOIN published_market.entity e ON e.id = l.entity_id AND e.register = current.register
            GROUP BY e.company_id, current.edition""", {"day": day, "register": register})
        companies = {company.id: company for company in self._companies("c.id = ANY(%(ids)s)",
                                                                          {"ids": [row["company_id"] for row in rows]})}
        return [Listed(companies[row["company_id"]], row["edition"], frozenset(row["kinds"])) for row in rows]

    def announcements(self, company_ids: Sequence[str]) -> Mapping[str, Sequence[Announcement]]:
        found: dict[str, list[Announcement]] = {}
        for row in self._rows("""
                SELECT m.target, m.document, m.address, r.citation, r.published_on
                FROM published_market.mention m
                JOIN published_market.release r ON r.id = m.document
                JOIN published_market.release_passage p ON p.release = m.document AND p.address = m.address
                WHERE m.kind = 'release' AND m.target_kind = 'company' AND m.target = ANY(%(ids)s)
                ORDER BY r.published_on DESC, m.document, p.ordinal""", {"ids": list(company_ids)}):
            found.setdefault(row["target"], []).append(
                Announcement(row["document"], row["address"], row["citation"], row["published_on"]))
        return found

    def company(self, company_id: str) -> Company | None:
        found = self._companies("c.id = %(id)s", {"id": company_id})
        return found[0] if found else None

    def register(self, register_id: str) -> Register | None:
        return self._registers().get(register_id)

    def industries(self) -> list[Industry]:
        return [Industry(row["source"], row["name"], row["register"], tuple(row["governed_by"]), tuple(row["reports"]),
                         tuple(row["datasets"]), row["published_at"])
                for row in self._rows("SELECT * FROM published_market.industry ORDER BY source, name")]

    def sectors(self) -> list[Sector]:
        return [Sector(row["id"], row["name"], row["name_en"],
                       tuple((item["source"], item["name"]) for item in row["industries"]), tuple(row["registers"]),
                       tuple(row["governed_by"]), tuple(row["reports"]), tuple(row["datasets"]), row["published_at"])
                for row in self._rows("SELECT * FROM published_market.sector ORDER BY id")]

    def dataset(self, dataset_id: str) -> Dataset | None:
        row = self._one("SELECT * FROM published_market.dataset d WHERE d.id = %(id)s", {"id": dataset_id})
        return _dataset(row) if row else None

    def datasets_matching(self, words: Sequence[str], source: str | None, limit: int) -> list[tuple[Dataset, float]]:
        if not words:
            return []
        rows = self._rows(f"""
            SELECT d.*, ts_rank({DATASET_WORDS}, query) AS score
            FROM published_market.dataset d, to_tsquery('simple', %(query)s) AS query
            WHERE {DATASET_WORDS} @@ query AND (%(source)s::text IS NULL OR d.source = %(source)s)
            ORDER BY score DESC, d.last_period DESC, d.id LIMIT %(limit)s""",
            {"query": _any_of(words), "source": source, "limit": limit})
        return [(_dataset(row), row["score"]) for row in rows]

    def series(self, series_ids: Sequence[str]) -> list[Series]:
        rows = self._rows("SELECT s.* FROM published_market.series s WHERE s.id = ANY(%(ids)s) ORDER BY s.id",
                          {"ids": list(series_ids)})
        return self._series(rows)

    def series_matching(self, dataset_ids: Sequence[str], words: Sequence[str], frequency: str | None,
                        limit: int) -> list[tuple[Series, float]]:
        if not words or not dataset_ids:
            return []
        rows = self._rows(f"""
            SELECT * FROM (
                SELECT s.*, ts_rank({SERIES_WORDS}, query, {BY_LENGTH}) AS score,
                       row_number() OVER (PARTITION BY s.dataset
                                          ORDER BY ts_rank({SERIES_WORDS}, query, {BY_LENGTH}) DESC, s.id) AS n
                FROM published_market.series s, to_tsquery('simple', %(query)s) AS query
                WHERE s.dataset = ANY(%(datasets)s)
                  AND (%(frequency)s::text IS NULL OR s.frequency = %(frequency)s)) AS ranked
            WHERE n <= %(limit)s ORDER BY dataset, n""",
            {"query": _any_of(words), "datasets": list(dataset_ids), "frequency": frequency, "limit": limit})
        return list(zip(self._series(rows), [row["score"] for row in rows], strict=True))

    def observations(self, series_ids: Sequence[str], start: date | None, end: date | None) -> Mapping[
        str, Sequence[ObservationRow]
    ]:
        found: dict[str, list[ObservationRow]] = {series_id: [] for series_id in series_ids}
        for row in self._rows("""
                SELECT series_id, period, value, provisional FROM published_market.observation
                WHERE series_id = ANY(%(ids)s)
                  AND (%(start)s::date IS NULL OR period >= %(start)s) AND (%(end)s::date IS NULL OR period <= %(end)s)
                ORDER BY series_id, period""", {"ids": list(series_ids), "start": start, "end": end}):
            found[row["series_id"]].append(ObservationRow(row["period"], row["value"], row["provisional"]))
        return found

    def report(self, report_id: str) -> Report | None:
        row = self._one("SELECT * FROM published_market.report WHERE id = %(id)s", {"id": report_id})
        return _report(row) if row else None

    def release(self, release_id: str) -> Release | None:
        row = self._one("SELECT * FROM published_market.release WHERE id = %(id)s", {"id": release_id})
        return _release(row) if row else None

    def passages(self, kind: str, document_id: str, address: str, window: int) -> list[Passage]:
        document = self.report(document_id) if kind == "report" else self.release(document_id)
        if document is None:
            return []
        table, pages = ("report_passage", "page_start, page_end") if kind == "report" else (
            "release_passage", "NULL::int AS page_start, NULL::int AS page_end")
        rows = self._rows(f"""
            WITH asked AS (SELECT ordinal FROM published_market.{table} WHERE {kind} = %(id)s AND address = %(address)s)
            SELECT p.address, p.ordinal, p.text, {pages}
            FROM published_market.{table} p, asked
            WHERE p.{kind} = %(id)s AND p.ordinal BETWEEN asked.ordinal - %(window)s AND asked.ordinal + %(window)s
            ORDER BY p.ordinal""", {"id": document_id, "address": address, "window": window})
        return [Passage(document, row["address"], row["ordinal"], row["text"], row["page_start"], row["page_end"])
                for row in rows]

    def every_passage(self) -> list[Passage]:
        reports = {row["id"]: _report(row) for row in self._rows("SELECT * FROM published_market.report", {})}
        releases = {row["id"]: _release(row) for row in self._rows("SELECT * FROM published_market.release", {})}
        rows = self._rows("""
            SELECT 'report' AS kind, report AS document, address, ordinal, text, page_start, page_end
            FROM published_market.report_passage
            UNION ALL
            SELECT 'release', release, address, ordinal, text, NULL, NULL FROM published_market.release_passage""", {})
        return [Passage((reports if row["kind"] == "report" else releases)[row["document"]], row["address"],
                        row["ordinal"], row["text"], row["page_start"], row["page_end"]) for row in rows]

    def every_dataset(self) -> list[Dataset]:
        return [_dataset(row) for row in self._rows("SELECT * FROM published_market.dataset d", {})]

    def mentions_of(self, target_kind: str, target: str) -> list[Mention]:
        return self._mentions(f"""
            SELECT m.* FROM published_market.mention m
            LEFT JOIN published_market.release r ON m.kind = 'release' AND r.id = m.document
            LEFT JOIN published_market.report rp ON m.kind = 'report' AND rp.id = m.document
            WHERE m.target_kind = %(kind)s AND m.target = %(target)s
            ORDER BY coalesce(r.published_on, rp.published_on) DESC NULLS LAST, m.document,
                     {ADDRESS_NUMBER.format(column="m.address")}""", {"kind": target_kind, "target": target})

    def mentions_in(self, kind: str, document_id: str, address: str | None) -> list[Mention]:
        return self._mentions(f"""
            SELECT m.* FROM published_market.mention m
            WHERE m.kind = %(kind)s AND m.document = %(id)s AND (%(address)s::text IS NULL OR m.address = %(address)s)
            ORDER BY {ADDRESS_NUMBER.format(column="m.address")}, m.target_kind, m.target""",
            {"kind": kind, "id": document_id, "address": address})

    def _companies(self, where: str, params: Mapping[str, Any]) -> list[Company]:
        rows = self._rows(f"SELECT c.* FROM published_market.company c WHERE {where} ORDER BY c.legal_name, c.id",
                          params)
        licences: dict[str, list[Row]] = {}
        for row in self._rows("""
                SELECT * FROM published_market.entity WHERE company_id = ANY(%(ids)s)
                ORDER BY company_id, first_listed NULLS LAST, license_number""", {"ids": [row["id"] for row in rows]}):
            licences.setdefault(row["company_id"], []).append(row)
        registers = self._registers()
        return [_company(row, registers[row["register"]], licences.get(row["id"], [])) for row in rows]

    def _series(self, rows: Sequence[Row]) -> list[Series]:
        dataset_ids = sorted({row["dataset"] for row in rows})
        datasets = {row["id"]: _dataset(row) for row in self._rows(
            "SELECT * FROM published_market.dataset d WHERE d.id = ANY(%(ids)s)", {"ids": dataset_ids})}
        return [Series(row["id"], datasets[row["dataset"]], row["label"], row["unit"], row["frequency"],
                       row["first_period"], row["last_period"], row["observations"]) for row in rows]

    def _mentions(self, query: str, params: Mapping[str, Any]) -> list[Mention]:
        return [Mention(row["kind"], row["document"], row["address"], row["target_kind"], row["target"])
                for row in self._rows(query, params)]

    def _registers(self) -> dict[str, Register]:
        return {row["id"]: Register(row["id"], row["issuer"], row["name"], row["newest_edition"], row["editions"],
                                    tuple(row["governed_by"]), tuple(row["reports"]), row["published_at"])
                for row in self._rows("SELECT * FROM published_market.register")}

    def _rows(self, query: str, params: Mapping[str, Any] | None = None) -> list[Row]:
        with self.connection.cursor(row_factory=dict_row) as cursor:
            return cursor.execute(query, params).fetchall()

    def _one(self, query: str, params: Mapping[str, Any] | None = None) -> Row | None:
        rows = self._rows(query, params)
        return rows[0] if rows else None


def _any_of(words: Sequence[str]) -> str:
    """A tsquery matching any of the words; each is a run of letters and digits, so nothing needs quoting."""
    return " | ".join(words)


def _company(row: Row, register: Register, entities: Sequence[Row]) -> Company:
    return Company(
        id=row["id"],
        register=register,
        legal_name=row["legal_name"],
        names=tuple(row["names"]),
        business_type=row["business_type"],
        status=row["status"],
        first_listed=row["first_listed"],
        left_after=row["left_after"],
        licences=tuple(Licence(entity["kind"], entity["license_number"], entity["license_date"], entity["first_listed"],
                               entity["last_listed"], entity["on_newest_list"], entity["left_after"])
                       for entity in entities),
        review_notes=tuple(note for entity in entities for note in entity["review_notes"]),
    )


def _dataset(row: Row) -> Dataset:
    return Dataset(row["id"], row["source"], row["industry"], row["group"], row["metric"], row["register"],
                   tuple(row["governed_by"]), tuple(row["reports"]), row["series"], row["first_period"],
                   row["last_period"], row["updated"], row["url"], row["citation"], row["published_at"])


def _report(row: Row) -> Report:
    return Report(row["id"], row["issuer"], row["family"], row["edition"], row["title"], row["published_on"],
                  row["language"], row["url"], row["citation"], row["pages"], row["passages"], row["method"],
                  row["published_at"])


def _release(row: Row) -> Release:
    return Release(row["id"], row["issuer"], row["number"], row["title"], row["published_on"], row["language"],
                   row["url"], row["citation"], row["passages"], row["published_at"])
