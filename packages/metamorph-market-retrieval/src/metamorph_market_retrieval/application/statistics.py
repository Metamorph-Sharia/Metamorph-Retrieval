"""find_series and get_observations: which statistics measure something, and their figures.

find_series looks in two stages: the datasets whose metric, group or industry hold the query's words, then their
series. Labels within a table differ mostly by row (a region, an account), and some say little alone ("Total DPK:
BUS"), so the dataset carries the meaning and the label picks the row: a series is ranked by the share of the query's
words its dataset and its label hold together. Values are never searched: get_observations reads them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from metamorph_market_retrieval.application.paging import offset_of
from metamorph_market_retrieval.application.ports import MarketReadModel, UnitFilter
from metamorph_market_retrieval.application.search import Meaning
from metamorph_market_retrieval.domain.evidence import series_evidence
from metamorph_market_retrieval.domain.fusion import reciprocal_rank_fusion
from metamorph_market_retrieval.domain.periods import period_range
from metamorph_market_retrieval.domain.records import Series
from metamorph_market_retrieval.domain.words import word_precision, word_score, words
from metamorph_retrieval_contract.errors import InvalidArgument, UnknownRef
from metamorph_retrieval_contract.evidence import EmptyReason, Evidence, Hit, MatchedBy, Page
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import DEFAULT_LIMIT, check_limit

FREQUENCIES = ("monthly", "quarterly", "semiannual", "annual")
DATASETS_CONSIDERED = 20  # tables sharing a metric's words (BPS's inflation by region, by group…) tie on them
SERIES_PER_DATASET = 3  # a page shows this many of a table's rows before more of one table
MAX_SERIES = 20
MAX_FIGURES = 120  # ten years of months: without a starting period, one call never floods the agent's context


@dataclass(frozen=True)
class SeriesQuery:
    query: str
    source: str | None = None  # ojk:portal, bi:seki, bps:table
    frequency: str | None = None
    limit: int = DEFAULT_LIMIT
    cursor: str | None = None

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise InvalidArgument("query: say what to measure, e.g. uang beredar luas")
        if self.frequency is not None and self.frequency not in FREQUENCIES:
            raise InvalidArgument(f"frequency {self.frequency!r}: monthly, quarterly, semiannual or annual")
        check_limit(self.limit)
        offset_of(self.cursor)


class FindSeries:
    """Two stages: rank the datasets, by their words and, with an index, by their cards' meaning, fused by rank;
    then the series of the best datasets by how much of the question the dataset and the label hold."""

    def __init__(self, read_model: MarketReadModel, per_dataset: int = SERIES_PER_DATASET, *,
                 meaning: Meaning | None = None) -> None:
        self.read_model = read_model
        self.per_dataset = per_dataset
        self.meaning = meaning

    def run(self, query: SeriesQuery) -> Page[Hit]:
        asked = words(query.query)
        by_words = [dataset.id for dataset, _ in self.read_model.datasets_matching(asked, query.source,
                                                                                  DATASETS_CONSIDERED)]
        by_meaning = self._by_meaning(query)
        fused = reciprocal_rank_fusion([by_words, by_meaning])
        if not fused:
            return Page.empty(EmptyReason.NO_MATCH)
        start = offset_of(query.cursor)
        wanted = start + query.limit + 1  # one more than the page, to know whether another follows
        # between datasets fused equal, the words' order, which already puts a table's successor before it
        words_order = {dataset_id: order for order, dataset_id in enumerate(by_words)}
        fused.sort(key=lambda item: (-item[1], words_order.get(item[0], len(by_words)), item[0]))
        dataset_order = {dataset_id: order for order, (dataset_id, _) in enumerate(fused)}
        found = self.read_model.series_matching(list(dataset_order), asked, query.frequency, wanted)
        scored = [(word_score(asked, f"{series.dataset.words_text()} {series.label}"), series, label_score)
                  for series, label_score in found]
        ranked = self._spread(sorted(scored, key=lambda item: (
            -item[0], -word_precision(asked, item[1].label), dataset_order[item[1].dataset.id], -item[2],
            item[1].id)))
        chosen = ranked[start : start + query.limit]
        if not chosen:
            return Page.empty(EmptyReason.NO_MATCH)
        hits = tuple(
            Hit(self._evidence(series), rank=rank, score=score,
                matched_by=_matched(score > 0 or series.dataset.id in by_words, series.dataset.id in by_meaning))
            for rank, (score, series, _) in enumerate(chosen, start=start + 1)
        )
        return Page(hits, cursor=str(start + query.limit) if len(ranked) > start + query.limit else None)

    def _by_meaning(self, query: SeriesQuery) -> list[str]:
        if self.meaning is None:
            return []
        matches = self.meaning.matches(query.query, UnitFilter(frozenset({"dataset"})), DATASETS_CONSIDERED)
        datasets = [self.read_model.dataset(match.ref.id) for match in matches]
        return [dataset.id for dataset in datasets
                if dataset is not None and (query.source is None or dataset.source == query.source)]

    def _evidence(self, series: Series) -> Evidence:
        evidence = series_evidence(series)
        if self.meaning is None:
            return evidence
        return replace(evidence, provenance=replace(evidence.provenance, index_version=self.meaning.index.version))

    def _spread(self, ranked: list[tuple[float, Series, float]]) -> list[tuple[float, Series, float]]:
        """The best few of each dataset first, then the rest, each part in rank order: one table's regional rows
        never fill a page that other tables also answer."""
        seen: dict[str, int] = {}
        first, rest = [], []
        for item in ranked:
            dataset = item[1].dataset.id
            seen[dataset] = seen.get(dataset, 0) + 1
            (first if seen[dataset] <= self.per_dataset else rest).append(item)
        return first + rest


@dataclass(frozen=True)
class ObservationsQuery:
    series: tuple[Ref, ...]
    start: str | None = None  # a period: 2026-08, 2026-Q2, 2026-S1, 2025
    end: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= len(self.series) <= MAX_SERIES:
            raise InvalidArgument(f"series: name one to {MAX_SERIES}")
        for ref in self.series:
            if ref.namespace != "series" or ref.address is not None:
                raise InvalidArgument(f"{ref} is not a series, such as series:bi:seki:tabel1_1:monthly:row=1")
        if self.start and self.end and period_range(self.start).start > period_range(self.end).start:
            raise InvalidArgument(f"from {self.start} is after to {self.end}")


class GetObservations:
    def __init__(self, read_model: MarketReadModel) -> None:
        self.read_model = read_model

    def run(self, query: ObservationsQuery) -> Page[Evidence]:
        ids = [ref.id for ref in query.series]
        known = {series.id: series for series in self.read_model.series(ids)}
        unknown = [str(ref) for ref in query.series if ref.id not in known]
        if unknown:
            raise UnknownRef(f"the market holds no series {', '.join(unknown)}")
        start = period_range(query.start).start if query.start else None
        end = period_range(query.end).end if query.end else None
        figures = self.read_model.observations(ids, start, end)
        items, warnings = [], []
        for series_id in ids:
            rows = list(figures.get(series_id, ()))
            if start is None and len(rows) > MAX_FIGURES:
                rows = rows[-MAX_FIGURES:]
                warnings.append(f"series:{series_id}: only the newest {MAX_FIGURES} figures; give from for older ones")
            items.append(series_evidence(known[series_id], rows))
        return Page(tuple(items), warnings=tuple(warnings))


def _matched(by_words: bool, by_meaning: bool) -> frozenset[MatchedBy]:
    return frozenset({*([MatchedBy.WORDS] if by_words else []), *([MatchedBy.SEMANTIC] if by_meaning else [])})
