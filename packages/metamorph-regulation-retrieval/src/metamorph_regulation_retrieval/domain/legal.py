"""Legal force and provision labels, in the platform's vocabulary.

A retrieval surface that tells an agent "Pasal 5" without saying whether it binds
is not usable for compliance. Legal force comes from the document's kind, and the
mapping is the platform's (`published.document.kind`), not ours.
"""

from __future__ import annotations

BINDING = "binding"
SHARIA = "sharia"
EXPLANATORY = "explanatory"
NONE = "none"

LEGAL_FORCE = {
    "law": BINDING,
    "regulation": BINDING,
    "implementing_rule": BINDING,
    "fatwa": SHARIA,
    "guideline": SHARIA,
    "circular": SHARIA,
    "explanatory": EXPLANATORY,
}

NUMBERED = {
    "pasal": "Pasal {}",
    "ayat": "ayat ({})",
    "huruf": "huruf {}",
    "angka": "angka {}",
    "bab": "BAB {}",
    "bagian": "Bagian {}",
    "paragraf": "Paragraf {}",
    "lampiran": "Lampiran {}",
    "diktum": "Diktum {}",
    "romawi": "{}",
}
ROMAN_NUMBERED = {"bab", "lampiran", "romawi"}
ROMAN = set("ivxlcdm")


def legal_force_of(kind: str | None) -> str:
    """Never guess: an unknown kind is `none`, and the caller can see the kind."""
    return LEGAL_FORCE.get((kind or "").lower(), NONE)


def provision_label(address: str) -> str:
    """`pasal-5/ayat-1/huruf-a` -> `Pasal 5 ayat (1) huruf a`.

    The same rendering the platform's stand-in uses, so a citation looks
    identical whichever provider answered.
    """
    return " ".join(_segment(segment) for segment in (address or "").split("/") if segment)


def _segment(segment: str) -> str:
    word, _, number = segment.partition("-")
    if word in NUMBERED and number:
        roman = word in ROMAN_NUMBERED or (word == "pasal" and set(number) <= ROMAN)
        return NUMBERED[word].format(number.upper() if roman else number)
    return " ".join(part.capitalize() for part in segment.split("-"))


FAMILY_LABELS = {
    "pojk": "POJK",
    "seojk": "SEOJK",
    "pbi": "PBI",
    "padg": "PADG",
    "uu": "UU",
    "pp": "PP",
    "fatwa": "Fatwa DSN-MUI",
    "permenaker": "Permenaker",
}


def document_citation(
    citation: str | None,
    family: str | None,
    number: str | None,
    year: int | None,
) -> str:
    """The document's citation, rebuilt from its own number and year when they
    disagree.

    `published.document.citation` is wrong for at least one document we serve:
    `ojk:pojk:2024:40` carries `POJK 10/POJK.05/2022`, the citation of the rule
    that amended it. Quoting that would put a wrong citation under a right
    passage, so a citation that names another number or year is rebuilt.
    """
    named = (citation or "").strip()
    number_matches = not number or number in named
    year_matches = not year or str(year) in named
    if named and number_matches and year_matches:
        return named

    label = FAMILY_LABELS.get((family or "").lower())
    if label and number and year:
        return f"{label} {number}/{year}"
    return named
