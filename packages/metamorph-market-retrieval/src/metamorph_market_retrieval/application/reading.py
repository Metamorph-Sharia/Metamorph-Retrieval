"""read and describe: any market ref, as evidence or as its card.

A passage can be read with up to MAX_WINDOW passages either side: match small, read big, when the agent asks.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from metamorph_market_retrieval.application.ports import MarketReadModel
from metamorph_market_retrieval.domain.evidence import (
    company_evidence,
    dataset_evidence,
    industry_evidence,
    passage_evidence,
    register_evidence,
    release_evidence,
    report_evidence,
    sector_evidence,
    series_evidence,
)
from metamorph_market_retrieval.domain.refs import industry_ref
from metamorph_retrieval_contract.errors import InvalidArgument, UnknownRef
from metamorph_retrieval_contract.evidence import Evidence
from metamorph_retrieval_contract.refs import Ref

MAX_WINDOW = 3


class Reading:
    def __init__(self, read_model: MarketReadModel) -> None:
        self.read_model = read_model
        self.wholes: dict[str, Callable[[str], Evidence | None]] = {
            "company": self._company,
            "register": self._register,
            "dataset": self._dataset,
            "series": self._series,
            "industry": self._industry,
            "sector": self._sector,
            "report": self._report,
            "release": self._release,
        }

    def read(self, ref: Ref, *, window: int = 0) -> Evidence:
        if not 0 <= window <= MAX_WINDOW:
            raise InvalidArgument(f"window {window}: 0 to {MAX_WINDOW} passages either side")
        evidence = self._passage(ref, window) if ref.address is not None else self._whole(ref)
        if evidence is None:
            raise UnknownRef(f"the market holds nothing under {ref}")
        return evidence

    def describe(self, refs: Sequence[Ref]) -> list[Evidence]:
        """Cards for the refs it holds, in the order asked; the others are left out."""
        cards = []
        for ref in refs:
            try:
                cards.append(self.read(ref).card())
            except UnknownRef:
                continue
        return cards

    def _whole(self, ref: Ref) -> Evidence | None:
        read = self.wholes.get(ref.namespace)
        return read(ref.id) if read else None

    def _passage(self, ref: Ref, window: int) -> Evidence | None:
        if ref.namespace not in ("report", "release") or ref.address is None:
            return None
        found = self.read_model.passages(ref.namespace, ref.id, ref.address, window)
        asked = next((passage for passage in found if passage.address == ref.address), None)
        if asked is None:
            return None
        return passage_evidence(asked, [passage for passage in found if passage is not asked])

    def _company(self, key: str) -> Evidence | None:
        company = self.read_model.company(key)
        return company_evidence(company) if company else None

    def _register(self, key: str) -> Evidence | None:
        register = self.read_model.register(key)
        return register_evidence(register) if register else None

    def _dataset(self, key: str) -> Evidence | None:
        dataset = self.read_model.dataset(key)
        return dataset_evidence(dataset) if dataset else None

    def _series(self, key: str) -> Evidence | None:
        found = self.read_model.series([key])
        return series_evidence(found[0]) if found else None

    def _industry(self, key: str) -> Evidence | None:
        wanted = Ref("industry", key)
        found = [item for item in self.read_model.industries() if industry_ref(item.source, item.name) == wanted]
        return industry_evidence(found[0]) if found else None

    def _sector(self, key: str) -> Evidence | None:
        found = [sector for sector in self.read_model.sectors() if sector.id == key]
        return sector_evidence(found[0]) if found else None

    def _report(self, key: str) -> Evidence | None:
        report = self.read_model.report(key)
        return report_evidence(report) if report else None

    def _release(self, key: str) -> Evidence | None:
        release = self.read_model.release(key)
        return release_evidence(release) if release else None
