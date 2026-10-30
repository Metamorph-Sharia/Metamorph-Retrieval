"""How a market record becomes evidence: cited as its source asks, qualified by what limits it, and never binding.

Everything the market holds has `legal_force: none`: what a regulator lists, counts, reports or announces. What a
record names (a register, a regulation, a report, a dataset) it names as `{"ref": …}` in its fields, for the agent
to follow and the gateway to enrich with the owner's citation.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import Any

from metamorph_market_retrieval.domain.periods import period_label
from metamorph_market_retrieval.domain.records import (
    Announcement,
    Company,
    Dataset,
    Industry,
    ObservationRow,
    Passage,
    Register,
    Release,
    Report,
    Sector,
    Series,
)
from metamorph_market_retrieval.domain.refs import doc_ref, industry_ref
from metamorph_retrieval_contract.evidence import (
    Body,
    Evidence,
    Figures,
    LegalForce,
    Observation,
    PageSpan,
    Provenance,
    Qualifiers,
    Record,
    Text,
)
from metamorph_retrieval_contract.refs import Ref

PROVIDER = "market"
INDEX_VERSION = "published-market-sql"  # read straight from published_market; an index arrives with search (M4)


def company_evidence(
    company: Company,
    *,
    standing: str | None = None,
    edition: date | None = None,
    announcements: Sequence[Announcement] = (),
) -> Evidence:
    """The company as its register's newest edition lists it, or as `edition` did, with that edition's `standing`."""
    register = company.register
    edition = edition or register.newest_edition
    fields: dict[str, Any] = {
        "register": _named("register", register.id),
        "names": list(company.names),
        "business_type": company.business_type,
        "first_listed": _day(company.first_listed),
        "left_after": _day(company.left_after),
        "licences": [
            {
                "kind": licence.kind,
                "number": licence.number,
                "granted_on": _day(licence.granted_on),
                "first_listed": _day(licence.first_listed),
                "last_listed": _day(licence.last_listed),
                "on_newest_list": licence.on_newest_list,
            }
            for licence in company.licences
        ],
        "review_notes": list(company.review_notes),
    }
    if announcements:
        fields["announcements"] = [
            {"ref": str(Ref("release", item.release, item.address)), "citation": item.citation,
             "published_on": item.published_on.isoformat()}
            for item in announcements
        ]
    return _evidence(
        Ref("company", company.id), "company", f"{register.issuer}, {register.name}, edisi {edition.isoformat()}",
        company.legal_name, Qualifiers(status=standing or company.status, as_of=edition), None, None, Record(fields),
        register.published_at,
    )


def register_evidence(register: Register) -> Evidence:
    fields = {
        "newest_edition": register.newest_edition.isoformat(),
        "editions": register.editions,
        "governed_by": _docs(register.governed_by),
        "reports": _refs("report", register.reports),
    }
    return _evidence(Ref("register", register.id), "register", f"{register.issuer}, {register.name}", register.name,
                     Qualifiers(as_of=register.newest_edition), None, None, Record(fields), register.published_at)


def dataset_evidence(dataset: Dataset) -> Evidence:
    fields = {
        "source": dataset.source,
        "industry": dataset.industry,
        "group": dataset.group,
        "register": _named("register", dataset.register) if dataset.register else None,
        "governed_by": _docs(dataset.governed_by),
        "reports": _refs("report", dataset.reports),
        "series": dataset.series_count,
        "first_period": dataset.first_period.isoformat(),
        "last_period": dataset.last_period.isoformat(),
    }
    return _evidence(Ref("dataset", dataset.id), "dataset", dataset.citation, dataset.metric,
                     Qualifiers(as_of=dataset.updated), None, dataset.url, Record(fields), dataset.published_at)


def series_evidence(series: Series, figures: Sequence[ObservationRow] | None = None) -> Evidence:
    """With figures, the series' values; without, its card for finding it."""
    dataset = series.dataset
    body: Body
    if figures is None:
        body = Record({
            "dataset": _named("dataset", dataset.id),
            "unit": series.unit,
            "frequency": series.frequency,
            "first_period": period_label(series.first_period, series.frequency),
            "last_period": period_label(series.last_period, series.frequency),
            "observations": series.observations,
        })
    else:
        body = Figures(series.unit, series.frequency, tuple(
            Observation(period_label(row.period, series.frequency), row.value, row.provisional) for row in figures
        ))
    provisional = any(row.provisional for row in figures or ())
    return _evidence(Ref("series", series.id), "series", dataset.citation, series.label,
                     Qualifiers(provisional=provisional, as_of=dataset.updated), None, dataset.url, body,
                     dataset.published_at)


def industry_evidence(industry: Industry) -> Evidence:
    fields = {
        "source": industry.source,
        "name": industry.name,
        "register": _named("register", industry.register) if industry.register else None,
        "governed_by": _docs(industry.governed_by),
        "reports": _refs("report", industry.reports),
        "datasets": _refs("dataset", industry.datasets),
    }
    return _evidence(industry_ref(industry.source, industry.name), "industry", f"{industry.name} ({industry.source})",
                     industry.name, Qualifiers(), None, None, Record(fields), industry.published_at)


def sector_evidence(sector: Sector) -> Evidence:
    fields = {
        "name_en": sector.name_en,
        "industries": [{"ref": str(industry_ref(source, name))} for source, name in sector.industries],
        "registers": _refs("register", sector.registers),
        "governed_by": _docs(sector.governed_by),
        "reports": _refs("report", sector.reports),
        "datasets": _refs("dataset", sector.datasets),
    }
    return _evidence(Ref("sector", sector.id), "sector", sector.name, sector.name, Qualifiers(), None, None,
                     Record(fields), sector.published_at)


def report_evidence(report: Report) -> Evidence:
    fields = {"issuer": report.issuer, "family": report.family, "edition": report.edition, "language": report.language,
              "pages": report.pages, "passages": report.passages, "method": report.method}
    return _evidence(Ref("report", report.id), "report", report.citation, report.title, Qualifiers(),
                     report.published_on, report.url, Record(fields), report.published_at)


def release_evidence(release: Release) -> Evidence:
    fields = {"issuer": release.issuer, "number": release.number, "language": release.language,
              "passages": release.passages}
    return _evidence(Ref("release", release.id), "release", release.citation, release.title, Qualifiers(),
                     release.published_on, release.url, Record(fields), release.published_at)


def passage_evidence(passage: Passage, neighbours: Iterable[Passage] = ()) -> Evidence:
    """A passage, as cited and embedded; with its neighbours, their words in reading order and the pages they span."""
    document = passage.document
    read = sorted([passage, *neighbours], key=lambda item: item.ordinal)
    pages = _pages(read)
    kind = "report" if isinstance(document, Report) else "release"
    citation = document.citation + (f", hlm. {page_numbers(pages)}" if pages else "")
    return _evidence(Ref(kind, document.id, passage.address), kind, citation, document.title, Qualifiers(),
                     document.published_on, document.url, Text("\n\n".join(item.text for item in read), pages),
                     document.published_at)


def _evidence(ref: Ref, kind: str, citation: str, title: str, qualifiers: Qualifiers, published_on: date | None,
              url: str | None, body: Body, published_at: datetime) -> Evidence:
    return Evidence(ref, kind, citation, title, LegalForce.NONE, qualifiers, published_on, url, body,
                    Provenance(PROVIDER, INDEX_VERSION, published_at))


def _pages(passages: Sequence[Passage]) -> PageSpan | None:
    starts = [item.page_start for item in passages if item.page_start is not None]
    ends = [item.page_end for item in passages if item.page_end is not None]
    return PageSpan(min(starts), max(ends)) if starts and ends else None


def page_numbers(pages: PageSpan) -> str:
    return str(pages.start) if pages.start == pages.end else f"{pages.start}–{pages.end}"


def _named(namespace: str, key: str) -> dict[str, str]:
    return {"ref": str(Ref(namespace, key))}


def _refs(namespace: str, keys: Iterable[str]) -> list[dict[str, str]]:
    return [_named(namespace, key) for key in keys]


def _docs(regulation_ids: Iterable[str]) -> list[dict[str, str]]:
    return [{"ref": str(doc_ref(regulation_id))} for regulation_id in regulation_ids]


def _day(value: date | None) -> str | None:
    return value.isoformat() if value else None
