"""A company's standing on a register edition, from the kinds of its records that edition lists.

The read contract gives each company's standing today. On a past date, the edition current that day decides it:
licensed if it listed one of the company's licenses, registered if only a registration.
"""

from __future__ import annotations

from collections.abc import Iterable


def standing_on(listed_kinds: Iterable[str]) -> str:
    kinds = set(listed_kinds)
    if "license" in kinds:
        return "licensed"
    if "registration" in kinds:
        return "registered"
    return "listed"  # listed with a number of neither form
