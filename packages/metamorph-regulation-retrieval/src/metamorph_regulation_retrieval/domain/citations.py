"""Parse an Indonesian legal citation into a ref we can resolve.

This is the one thing our retrieval can do that a general search on the same
corpus cannot: "POJK 40/2024 Pasal 137 ayat (3)" is not a similarity query, it is
an address. The patterns mirror the identifier router measured on the acceptance
set (14 of 15 correct), kept here so the served tool and the benchmark agree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .refs import RefError, make_ref

DOCUMENT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bPOJK\s*(?:No\.?|Nomor)?\s*(\d+)\s*/\s*[A-Za-z0-9.]+\s*/\s*(\d{4})", re.I), "ojk:pojk"),
    (re.compile(r"\bPOJK\s*(?:No\.?|Nomor)?\s*(\d+)\s*(?:/|Tahun)\s*(\d{4})", re.I), "ojk:pojk"),
    (re.compile(r"\bSEOJK\s*(?:No\.?|Nomor)?\s*(\d+)\s*/\s*[A-Za-z0-9.]+\s*/\s*(\d{4})", re.I), "ojk:seojk"),
    (re.compile(r"\bSEOJK\s*(?:No\.?|Nomor)?\s*(\d+)\s*(?:/|Tahun)\s*(\d{4})", re.I), "ojk:seojk"),
    (
        re.compile(
            r"\b(?:UU|Undang-Undang)(?:\s+PDP)?\s*(?:No\.?|Nomor)?\s*(\d+)\s*(?:/|Tahun)\s*(\d{4})",
            re.I,
        ),
        "id:uu",
    ),
    (re.compile(r"\bPP\s*(?:No\.?|Nomor)?\s*(\d+)\s*(?:/|Tahun)\s*(\d{4})", re.I), "id:pp"),
    (re.compile(r"\bPADG\s*(?:No\.?|Nomor)?\s*(\d+)\s*(?:/|Tahun)\s*(\d{4})", re.I), "bi:padg"),
    (re.compile(r"\bPBI\s*(?:No\.?|Nomor)?\s*(\d+)\s*(?:/|Tahun)\s*(\d{4})", re.I), "bi:pbi"),
)

FATWA = re.compile(r"\bFatwa\s*(?:DSN[- ]MUI)?\s*(?:No\.?|Nomor)?\s*(\d+)", re.I)

PASAL = re.compile(r"\bPasal\s+(\d+)", re.I)
AYAT = re.compile(r"\bayat\s*\(?\s*(\d+)\s*\)?", re.I)
HURUF = re.compile(r"\bhuruf\s*\(?\s*([a-z])\s*\)?", re.I)
DIKTUM = re.compile(r"\bDiktum\s+(\w+)(?:\s+angka\s+([\d\-–]+))?", re.I)


@dataclass(frozen=True)
class Citation:
    document_id: str
    address: str | None = None

    @property
    def ref(self) -> str:
        return make_ref(self.document_id, self.address)


def parse_citation(text: str) -> Citation:
    """`POJK 40/2024 Pasal 137 ayat (3)` -> `ojk:pojk:2024:40`, `pasal-137/ayat-3`."""
    value = (text or "").strip()
    if not value:
        raise RefError("give a citation, such as 'POJK 40/2024 Pasal 137 ayat (3)'")

    document_id = _document(value)
    return Citation(document_id, _address(value))


def _document(value: str) -> str:
    found = _fatwa(value) or _numbered(value)
    if found is None:
        raise RefError(
            "could not read a regulation from the citation; name the instrument, "
            "such as 'POJK 40/2024', 'Fatwa 117', 'UU 27/2022', or 'SEOJK 19/2025'"
        )
    return found


def _fatwa(value: str) -> str | None:
    match = FATWA.search(value)
    return f"dsnmui:fatwa:{match.group(1)}" if match else None


def _numbered(value: str) -> str | None:
    for pattern, prefix in DOCUMENT_PATTERNS:
        match = pattern.search(value)
        if match:
            return f"{prefix}:{match.group(2)}:{match.group(1)}"
    return None


def _address(value: str) -> str | None:
    pasal = PASAL.search(value)
    if pasal:
        address = f"pasal-{pasal.group(1)}"
        ayat = AYAT.search(value, pasal.end())
        if ayat:
            address += f"/ayat-{ayat.group(1)}"
            huruf = HURUF.search(value, ayat.end())
            if huruf:
                address += f"/huruf-{huruf.group(1).lower()}"
        return address

    diktum = DIKTUM.search(value)
    if diktum:
        base = f"diktum-{diktum.group(1).lower()}"
        if not diktum.group(2):
            return base
        numbers = re.findall(r"\d+", diktum.group(2))
        return f"{base}/angka-{numbers[0]}" if numbers else base

    return None
