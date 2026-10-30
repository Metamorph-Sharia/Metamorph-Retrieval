from datetime import date

import pytest

from metamorph_market_retrieval.domain.periods import PeriodRange, period_label, period_range
from metamorph_market_retrieval.domain.refs import NAMESPACES, doc_ref, industry_ref, slug
from metamorph_retrieval_contract.errors import InvalidArgument
from metamorph_retrieval_contract.refs import Ref


def test_an_industrys_ref_is_its_source_and_its_name_as_a_slug() -> None:
    name = "Layanan Pendanaan Bersama Berbasis Teknologi Informasi (LPBBTI) Syariah"

    assert slug(name) == "layanan-pendanaan-bersama-berbasis-teknologi-informasi-lpbbti-syariah"
    assert industry_ref("ojk:portal", "Bank Umum Syariah") == Ref("industry", "ojk:portal:bank-umum-syariah")


def test_a_regulation_the_market_names_is_a_doc_ref_it_doesnt_own() -> None:
    assert doc_ref("ojk:pojk:2024:40") == Ref.parse("doc:ojk:pojk:2024:40")
    assert "doc" not in NAMESPACES


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("2026-08", date(2026, 8, 1), date(2026, 8, 31)),
        ("2026-02", date(2026, 2, 1), date(2026, 2, 28)),
        ("2026-Q2", date(2026, 4, 1), date(2026, 6, 30)),
        ("2026-S2", date(2026, 7, 1), date(2026, 12, 31)),
        ("2025", date(2025, 1, 1), date(2025, 12, 31)),
    ],
)
def test_a_period_covers_its_days(text: str, start: date, end: date) -> None:
    assert period_range(text) == PeriodRange(start, end)


@pytest.mark.parametrize("text", ["2026-13", "2026-Q5", "Agustus 2026", "26-08"])
def test_a_period_not_written_as_the_contract_writes_it_is_refused(text: str) -> None:
    with pytest.raises(InvalidArgument, match="is not a period, such as 2026-08, 2026-Q2, 2026-S1 or 2025"):
        period_range(text)


@pytest.mark.parametrize(
    ("first_day", "frequency", "label"),
    [
        (date(2026, 8, 1), "monthly", "2026-08"),
        (date(2026, 4, 1), "quarterly", "2026-Q2"),
        (date(2026, 7, 1), "semiannual", "2026-S2"),
        (date(2025, 1, 1), "annual", "2025"),
    ],
)
def test_an_observation_is_labelled_by_its_series_frequency(first_day: date, frequency: str, label: str) -> None:
    assert period_label(first_day, frequency) == label
    assert period_range(label).start == first_day
