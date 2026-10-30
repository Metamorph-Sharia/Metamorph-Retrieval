"""The read model in memory, over the samples: what the use cases are tested against.

Simple on purpose: word overlap stands in for PostgreSQL's full text, and lists keep their insertion order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime

from market_samples import (
    ALAMI,
    INVESTREE,
    LPBBTI,
    LPBBTI_SYARIAH,
    M2,
    M2_FIGURES,
    PUBLISHED_AT,
    REVOCATION,
    REVOCATION_RELEASE,
    REVOKED,
    ROADMAP,
    SEKI_1_1,
    SHARIA_BANKING,
    TARGETS,
)

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
from metamorph_market_retrieval.domain.words import word_score

DANA_SYARIAH = replace(ALAMI, id="ojk:lpbbti:kep-10-d.05-2021", legal_name="PT Dana Syariah Indonesia",
                       names=("DANA SYARIAH",), licences=(
                           Licence("registration", "S-2/NB.213/2019", date(2019, 3, 5), date(2019, 12, 20),
                                   date(2021, 2, 1), False, None),
                           Licence("license", "KEP-10/D.05/2021", date(2021, 2, 1), date(2021, 2, 26),
                                   date(2026, 7, 31), True, None)))
BANK_UMUM_SYARIAH = replace(LPBBTI_SYARIAH, name="Bank Umum Syariah", register=None,
                            governed_by=("id:uu:2008:21", "ojk:pojk:2022:16"), reports=("ojk:roadmap:2023:rp3si",),
                            datasets=())
BEFORE_TARGETS = Passage(ROADMAP, "p-42", 42, "pengembangan ekosistem serta pengembangan infrastruktur…", 60, 61)
AFTER_TARGETS = Passage(ROADMAP, "p-44", 44, "Meningkatnya Efektivitas Pengaturan, Pengawasan, dan Perizinan…", 62, 63)
EDITION_2020 = date(2020, 6, 29)
M1 = replace(M2, id="bi:seki:tabel1_1:monthly:row=2",
             label="UANG BEREDAR DAN FAKTOR-FAKTOR YANG MEMPENGARUHINYA: Uang Beredar Sempit (M1)")
QUASI_MONEY = replace(M2, id="bi:seki:tabel1_1:monthly:row=10",  # a sub-row: its label repeats its parent's path
                      label="UANG BEREDAR DAN FAKTOR-FAKTOR YANG MEMPENGARUHINYA: Uang Beredar Luas(M2) › Uang Kuasi")
RETIRED_TABLE = replace(SEKI_1_1, id="bi:seki:tabel1_0", last_period=date(2014, 12, 1))  # the same words, retired
RETIRED_M2 = replace(M2, id="bi:seki:tabel1_0:monthly:row=1", dataset=RETIRED_TABLE)


class MemoryMarket:
    def __init__(self) -> None:
        self.all_companies = [ALAMI, DANA_SYARIAH, INVESTREE]
        self.editions = {  # (register, edition) → the companies it listed, with their records' kinds
            ("ojk:lpbbti", EDITION_2020): [(ALAMI, {"license"}), (DANA_SYARIAH, {"registration"}),
                                           (INVESTREE, {"license"})],
            ("ojk:lpbbti", LPBBTI.newest_edition): [(ALAMI, {"license"}), (DANA_SYARIAH, {"license"})],
        }
        self.all_announcements = {INVESTREE.id: [REVOCATION]}
        self.all_industries = [LPBBTI_SYARIAH, BANK_UMUM_SYARIAH]
        self.all_sectors = [SHARIA_BANKING]
        self.all_series = [M1, M2, QUASI_MONEY, RETIRED_M2]
        self.figures = {M2.id: list(M2_FIGURES)}
        self.all_passages = [BEFORE_TARGETS, TARGETS, AFTER_TARGETS, REVOKED]
        self.all_mentions = [
            Mention("release", REVOCATION_RELEASE.id, "p-1", "company", INVESTREE.id),
            Mention("release", REVOCATION_RELEASE.id, "p-1", "regulation", "ojk:pojk:2022:10"),
            Mention("report", ROADMAP.id, "p-44", "regulation", "ojk:pojk:2024:40"),
        ]

    def published_at(self) -> datetime | None:
        return PUBLISHED_AT

    def companies(self, register: str | None, status: str | None, business_type: str | None) -> list[Company]:
        return [company for company in self.all_companies
                if (register is None or company.register.id == register)
                and (status is None or company.status == status)
                and (business_type is None or company.business_type == business_type)]

    def listed_on(self, register: str | None, day: date) -> list[Listed]:
        current: dict[str, date] = {}
        for listed_register, edition in self.editions:
            if edition <= day and (register is None or listed_register == register):
                current[listed_register] = max(edition, current.get(listed_register, edition))
        return [Listed(company, edition, frozenset(kinds))
                for listed_register, edition in current.items()
                for company, kinds in self.editions[(listed_register, edition)]]

    def announcements(self, company_ids: Sequence[str]) -> Mapping[str, Sequence[Announcement]]:
        return {company_id: self.all_announcements[company_id] for company_id in company_ids
                if company_id in self.all_announcements}

    def company(self, company_id: str) -> Company | None:
        return next((company for company in self.all_companies if company.id == company_id), None)

    def register(self, register_id: str) -> Register | None:
        return LPBBTI if register_id == LPBBTI.id else None

    def industries(self) -> list[Industry]:
        return self.all_industries

    def sectors(self) -> list[Sector]:
        return self.all_sectors

    def dataset(self, dataset_id: str) -> Dataset | None:
        return next((dataset for dataset in [SEKI_1_1, RETIRED_TABLE] if dataset.id == dataset_id), None)

    def datasets_matching(self, words: Sequence[str], source: str | None, limit: int) -> list[tuple[Dataset, float]]:
        scored = [(dataset, word_score(words, dataset.words_text()))
                  for dataset in [SEKI_1_1, RETIRED_TABLE] if source is None or dataset.source == source]
        ranked = sorted(scored, key=lambda pair: (-pair[1], -pair[0].last_period.toordinal(), pair[0].id))
        return [(dataset, score) for dataset, score in ranked if score][:limit]

    def series(self, series_ids: Sequence[str]) -> list[Series]:
        return sorted((series for series in self.all_series if series.id in series_ids), key=lambda series: series.id)

    def series_matching(self, dataset_ids: Sequence[str], words: Sequence[str], frequency: str | None,
                        limit: int) -> list[tuple[Series, float]]:
        scored = [(series, word_score(words, series.label)) for series in self.all_series
                  if series.dataset.id in dataset_ids and (frequency is None or series.frequency == frequency)]
        return sorted(scored, key=lambda pair: (-pair[1], pair[0].id))[:limit]

    def observations(self, series_ids: Sequence[str], start: date | None, end: date | None) -> Mapping[
        str, Sequence[ObservationRow]
    ]:
        return {series_id: [row for row in self.figures.get(series_id, [])
                            if (start is None or row.period >= start) and (end is None or row.period <= end)]
                for series_id in series_ids}

    def report(self, report_id: str) -> Report | None:
        return ROADMAP if report_id == ROADMAP.id else None

    def release(self, release_id: str) -> Release | None:
        return REVOCATION_RELEASE if release_id == REVOCATION_RELEASE.id else None

    def passages(self, kind: str, document_id: str, address: str, window: int) -> list[Passage]:
        of_document = [passage for passage in self.all_passages if passage.document.id == document_id]
        asked = next((passage for passage in of_document if passage.address == address), None)
        if asked is None:
            return []
        return [passage for passage in of_document if abs(passage.ordinal - asked.ordinal) <= window]

    def mentions_of(self, target_kind: str, target: str) -> list[Mention]:
        return [mention for mention in self.all_mentions
                if (mention.target_kind, mention.target) == (target_kind, target)]

    def mentions_in(self, kind: str, document_id: str, address: str | None) -> list[Mention]:
        return [mention for mention in self.all_mentions if (mention.kind, mention.document) == (kind, document_id)
                and (address is None or mention.address == address)]

    def every_passage(self) -> list[Passage]:
        return list(self.all_passages)

    def every_dataset(self) -> list[Dataset]:
        return list({series.dataset.id: series.dataset for series in self.all_series}.values())
