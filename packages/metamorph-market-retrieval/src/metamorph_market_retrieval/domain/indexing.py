"""What the index holds for each unit: the platform's own passages, and cards for datasets, industries and sectors,
never re-chunked, each with the text it is found by. A deterministic header puts back what a passage lifted from its
document lacks: which report and pages, or which release and its title (often the company or the rule a later
passage doesn't name).

Full text and the embedding read the same text, so the two rankings fused judge the same thing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from functools import cached_property

from metamorph_market_retrieval.domain.evidence import page_numbers
from metamorph_market_retrieval.domain.records import Dataset, Industry, Passage, Report, Sector
from metamorph_market_retrieval.domain.refs import industry_ref
from metamorph_retrieval_contract.evidence import PageSpan
from metamorph_retrieval_contract.refs import Ref


@dataclass(frozen=True)
class IndexUnit:
    ref: Ref
    kind: str  # report, release, dataset
    document: Ref | None  # a passage's whole report or release
    issuer: str | None
    published_on: date | None
    text: str

    @cached_property
    def text_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()


def passage_unit(passage: Passage) -> IndexUnit:
    document = passage.document
    if isinstance(document, Report):
        kind = "report"
        pages = PageSpan(passage.page_start, passage.page_end) if passage.page_start and passage.page_end else None
        header = document.citation + (f", hlm. {page_numbers(pages)}" if pages else "")
    else:
        kind = "release"
        header = f"{document.citation}: {document.title}"
    return IndexUnit(ref=Ref(kind, document.id, passage.address), kind=kind, document=Ref(kind, document.id),
                     issuer=document.issuer, published_on=document.published_on, text=f"{header}\n{passage.text}")


def dataset_unit(dataset: Dataset) -> IndexUnit:
    described = "; ".join(part for part in (dataset.group, dataset.industry, dataset.citation) if part)
    span = f"{dataset.first_period:%Y-%m} – {dataset.last_period:%Y-%m}"
    return IndexUnit(ref=Ref("dataset", dataset.id), kind="dataset", document=None,
                     issuer=dataset.source.split(":")[0], published_on=dataset.updated,
                     text=f"{dataset.metric}\n{described}; {span}")


def industry_unit(industry: Industry) -> IndexUnit:
    return IndexUnit(ref=industry_ref(industry.source, industry.name), kind="industry", document=None,
                     issuer=industry.source.split(":")[0], published_on=None,
                     text=f"{industry.name}\n{industry.source}")


def sector_unit(sector: Sector) -> IndexUnit:
    return IndexUnit(ref=Ref("sector", sector.id), kind="sector", document=None, issuer=None, published_on=None,
                     text="\n".join(name for name in (sector.name, sector.name_en) if name))
