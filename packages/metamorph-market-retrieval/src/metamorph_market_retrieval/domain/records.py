"""What the read model returns: published_market's rows, as plain values. Ids are the read contract's own.

Periods are kept as their first day, as the read contract stores them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Register:
    id: str
    issuer: str
    name: str
    newest_edition: date
    editions: int
    governed_by: tuple[str, ...]  # regulation ids
    reports: tuple[str, ...]
    published_at: datetime


@dataclass(frozen=True)
class Licence:
    """One of a company's records on its register: a license or a registration."""

    kind: str  # license, registration, unknown
    number: str
    granted_on: date | None
    first_listed: date | None
    last_listed: date | None
    on_newest_list: bool
    left_after: date | None


@dataclass(frozen=True)
class Company:
    id: str
    register: Register
    legal_name: str
    names: tuple[str, ...]  # every other legal and platform name
    business_type: str
    status: str  # licensed, registered, left: as of the register's newest edition
    first_listed: date | None
    left_after: date | None
    licences: tuple[Licence, ...]
    review_notes: tuple[str, ...]


@dataclass(frozen=True)
class Announcement:
    """A release passage that names a company."""

    release: str
    address: str
    citation: str
    published_on: date


@dataclass(frozen=True)
class Dataset:
    id: str
    source: str
    industry: str | None  # None for a macro dataset
    group: str
    metric: str
    register: str | None
    governed_by: tuple[str, ...]
    reports: tuple[str, ...]
    series_count: int
    first_period: date
    last_period: date
    updated: date | None
    url: str
    citation: str
    published_at: datetime

    def words_text(self) -> str:
        """What a dataset is found by: its metric, group and industry, as the source names them."""
        return f"{self.metric} {self.group} {self.industry or ''}"


@dataclass(frozen=True)
class Series:
    id: str
    dataset: Dataset
    label: str
    unit: str | None
    frequency: str
    first_period: date
    last_period: date
    observations: int


@dataclass(frozen=True)
class ObservationRow:
    period: date  # its first day
    value: float
    provisional: bool


@dataclass(frozen=True)
class Industry:
    source: str
    name: str
    register: str | None
    governed_by: tuple[str, ...]
    reports: tuple[str, ...]
    datasets: tuple[str, ...]
    published_at: datetime


@dataclass(frozen=True)
class Sector:
    id: str
    name: str
    name_en: str | None
    industries: tuple[tuple[str, str], ...]  # (source, name), in the curator's order
    registers: tuple[str, ...]
    governed_by: tuple[str, ...]
    reports: tuple[str, ...]
    datasets: tuple[str, ...]
    published_at: datetime


@dataclass(frozen=True)
class Report:
    id: str
    issuer: str
    family: str
    edition: str
    title: str
    published_on: date | None
    language: str
    url: str | None
    citation: str
    pages: int
    passages: int
    method: str
    published_at: datetime


@dataclass(frozen=True)
class Release:
    id: str
    issuer: str
    number: str | None
    title: str
    published_on: date
    language: str
    url: str | None
    citation: str
    passages: int
    published_at: datetime


@dataclass(frozen=True)
class Passage:
    document: Report | Release
    address: str
    ordinal: int
    text: str
    page_start: int | None  # a release has no pages
    page_end: int | None


@dataclass(frozen=True)
class Listed:
    """A company on one edition of its register, with the kinds of its records that edition listed."""

    company: Company
    edition: date
    kinds: frozenset[str]


@dataclass(frozen=True)
class Mention:
    """A report's or a release's passage naming a regulation or a company."""

    kind: str  # report, release
    document: str
    address: str
    target_kind: str  # regulation, company
    target: str
