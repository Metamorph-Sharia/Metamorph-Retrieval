"""Periods as the contract writes them: a month (2026-08), a quarter (2026-Q2), a half-year (2026-S1), a year (2025).

The read contract stores a period as its first day; its series' frequency says how long it is.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

from metamorph_retrieval_contract.errors import InvalidArgument

PERIOD = re.compile(r"(?P<year>\d{4})(?:-(?:(?P<month>0[1-9]|1[0-2])|Q(?P<quarter>[1-4])|S(?P<half>[12])))?")
MONTHS_IN = {"quarter": 3, "half": 6}


@dataclass(frozen=True)
class PeriodRange:
    start: date
    end: date


def period_range(text: str) -> PeriodRange:
    match = PERIOD.fullmatch(text)
    if not match:
        raise InvalidArgument(f"{text!r} is not a period, such as 2026-08, 2026-Q2, 2026-S1 or 2025")
    year = int(match["year"])
    if match["month"]:
        return _months(year, int(match["month"]), 1)
    for part, length in MONTHS_IN.items():
        if match[part]:
            return _months(year, (int(match[part]) - 1) * length + 1, length)
    return _months(year, 1, 12)


def period_label(first_day: date, frequency: str) -> str:
    if frequency == "monthly":
        return f"{first_day.year}-{first_day.month:02d}"
    if frequency == "quarterly":
        return f"{first_day.year}-Q{(first_day.month - 1) // 3 + 1}"
    if frequency == "semiannual":
        return f"{first_day.year}-S{(first_day.month - 1) // 6 + 1}"
    return str(first_day.year)


def _months(year: int, first: int, count: int) -> PeriodRange:
    last = first + count - 1
    return PeriodRange(date(year, first, 1), date(year, last, calendar.monthrange(year, last)[1]))
