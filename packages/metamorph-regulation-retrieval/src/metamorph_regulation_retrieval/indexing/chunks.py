"""One chunk per provision: clean the text, flag what is not worth searching, and
build the context the model sees.

Every provision is a chunk, so any published address can be read. Only the
platform's retrieval units are searched (`published.provision_unit`: the smallest
provisions with wording of their own, a paragraph holding its lettered items),
since a doc: ref's address is a unit's (the retrieval contract). A paragraph and
the article holding it then never compete for one place in a ranking, and neither
does an item with its paragraph.

The recipe is the one measured on the benchmark: the provision's own wording,
prefixed with its document title and the address written as a lawyer writes it.
Splitting over-long provisions was tested and lost on ranking, so it is not done
here; the model truncates at its sequence length instead, and the `token_count`
column records how long the context was so that truncation is visible.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

PAGE_MARKER = re.compile(r"<!--\s*page\s+\d+\s*-->", re.I)
URL = re.compile(r"https?://\S+")
SPACES = re.compile(r"[ \t]+")
BLANK_LINES = re.compile(r"\n{3,}")
STRUCTURAL = re.compile(
    r"^(pasal|ayat|bab|bagian|paragraf|huruf|angka|diktum)\s+[ivxlc0-9a-z]+[.)]?$", re.I
)
NO_INFORMATION = {"cukup jelas", "dihapus", "tidak ada", "tidak diatur", "-", ""}

# A chunk is searchable unless it is one of these. `not_a_unit` is the bulk: an
# article holding paragraphs, or an item inside one. Of the rest, `cukup_jelas` is
# most: an article that says "sufficiently clear" carries no text.
UNSEARCHABLE = {"not_a_unit", "no_information", "cukup_jelas", "dihapus", "structural"}

LANGUAGE = "indonesian"  # the regulations' language; its stemmer joins pembiayaan and dibiayai
# The stems a word search can use: each stem's number of units, and whether it is common. Its stop words are the
# corpus's own (yang, dan, pada, but also pasal, ayat, wajib): the `indonesian` configuration keeps every word, and
# a stem most units hold tells a search little while making it match nearly everything.
COMMON_SHARE = 0.05
STEMS_DDL = """
create table {stems} as
select word, ndoc, ndoc > {share} * (select count(*) from {chunks} where searchable) as common
from ts_stat('select words from {chunks} where searchable')
"""

PROVISIONS = """
select p.document_id, p.text_sha256, p.address, p.kind, p.label, p.heading,
       d.issuer, d.status, p.valid_from, p.valid_to, p.body, d.title, d.citation,
       u.address is not null as unit
from published.provision p
join published.document d on d.id = p.document_id
left join published.provision_unit u on u.document_id = p.document_id and u.address = p.address
where p.body <> '' and p.document_id <> all(%s)
order by p.document_id, p.address
"""

# `revoked_on` is the earliest dated revocation of the whole document; `in_force_on`
# filters on it. A document revoked without a dated event has none, and counts as
# revoked on any day (its status says so today, and nothing says since when).
DOCUMENTS = """
select d.id, d.kind, d.citation, d.title, d.issuer, d.status, d.family, d.number,
       d.year, d.promulgated_on, d.effective_on, d.published_at, d.aliases,
       (select min(e.effective_from) from published.status_event e
        where e.document_id = d.id and e.address is null and e.status = 'revoked') as revoked_on
from published.document d
where d.id <> all(%s)
order by d.id
"""

CHUNK_DDL = """
create table {table} (
  chunk_id text primary key,
  snapshot_id text not null,
  document_id text not null,
  text_sha256 text not null,
  source_address text not null,
  address text not null,
  part integer not null default 0,
  part_count integer not null default 1,
  kind text not null,
  label text,
  heading text,
  title text not null,
  citation text not null,
  issuer text not null,
  doc_status text not null,
  valid_from date,
  valid_to date,
  body text not null,
  body_md5 text not null,
  body_chars integer not null,
  context_text text not null,
  context_hash text not null,
  token_count integer not null,
  searchable boolean not null,
  flags text[] not null,
  words tsvector generated always as (
    case when searchable then to_tsvector('""" + LANGUAGE + """', context_text) end) stored
)
"""

META_DDL = """
create table {table} (
  document_id text primary key,
  kind text not null,
  citation text,
  title text,
  issuer text,
  status text,
  family text,
  number text,
  year integer,
  promulgated_on date,
  effective_on date,
  published_at timestamptz,
  aliases text[],
  revoked_on date
)
"""


@dataclass(frozen=True)
class Provision:
    document_id: str
    text_sha256: str
    address: str
    kind: str
    label: str | None
    heading: str | None
    issuer: str
    status: str
    valid_from: object
    valid_to: object
    body: str
    title: str
    citation: str | None
    unit: bool = True  # a retrieval unit (published.provision_unit)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    text_sha256: str
    source_address: str
    address: str
    kind: str
    label: str | None
    heading: str | None
    title: str
    citation: str
    issuer: str
    doc_status: str
    valid_from: object
    valid_to: object
    body: str
    context_text: str
    token_count: int
    searchable: bool
    flags: list[str]


def clean(text: str) -> tuple[str, bool]:
    """Normalise the wording; report whether page markers were removed."""
    had_page_markers = bool(PAGE_MARKER.search(text))
    text = PAGE_MARKER.sub("\n\n", text)
    text = URL.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = SPACES.sub(" ", text)
    text = BLANK_LINES.sub("\n\n", text)
    return text.strip(), had_page_markers


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def provision_label(address: str) -> str:
    """`pasal-137/ayat-3/huruf-b` -> `Pasal 137, ayat (3), huruf b`.

    The comma-separated form is the one the service already returns to callers, so
    the context a model reads is the context a user sees.
    """
    labels: list[str] = []
    for part in address.split("/"):
        if part.startswith("pasal-"):
            value = part.removeprefix("pasal-")
            labels.append("Pasal " + (value.upper() if value.isalpha() else value))
        elif part.startswith("ayat-"):
            labels.append(f"ayat ({part.removeprefix('ayat-')})")
        elif part.startswith("huruf-"):
            labels.append("huruf " + part.removeprefix("huruf-"))
        elif part.startswith("angka-"):
            labels.append("angka " + part.removeprefix("angka-"))
        elif part.startswith("diktum-"):
            labels.append("Diktum " + part.removeprefix("diktum-").title())
        elif part.startswith("lampiran-"):
            labels.append("Lampiran " + part.removeprefix("lampiran-").title())
        elif part.startswith("romawi-"):
            labels.append("Romawi " + part.removeprefix("romawi-").title())
        elif part.startswith("bab-"):
            labels.append("Bab " + part.removeprefix("bab-").title())
        elif part.startswith("bagian-"):
            labels.append("Bagian " + part.removeprefix("bagian-").title())
        elif part.startswith("paragraf-"):
            labels.append("Paragraf " + part.removeprefix("paragraf-"))
        elif part == "penjelasan":
            labels.append("Penjelasan")
        elif part == "menimbang":
            labels.append("Menimbang")
        elif part == "mengingat":
            labels.append("Mengingat")
        elif part == "memperhatikan":
            labels.append("Memperhatikan")
        else:
            labels.append(part.replace("-", " ").title())
    return ", ".join(labels)


def significance_flags(body: str, label: str | None, heading: str | None) -> list[str]:
    """Why a provision might not be worth searching. Stored, not hidden."""
    normalised = re.sub(r"\s+", " ", body).strip().lower().rstrip(".")
    flags: list[str] = []
    if normalised in NO_INFORMATION:
        flags.append("no_information")
    if "cukup jelas" in normalised:
        flags.append("cukup_jelas")
    if "dihapus" in normalised:
        flags.append("dihapus")
    if STRUCTURAL.fullmatch(normalised):
        flags.append("structural")
    if label and "cukup jelas" in label.lower():
        flags.append("cukup_jelas")
    if label and "dihapus" in label.lower():
        flags.append("dihapus")
    if heading and STRUCTURAL.fullmatch(heading.strip().lower().rstrip(".")):
        flags.append("structural")
    return flags


def chunk(provision: Provision, snapshot: str) -> Chunk:
    body, had_page_markers = clean(provision.body)
    flags = significance_flags(body, provision.label, provision.heading)
    if not provision.unit:
        flags.append("not_a_unit")
    if had_page_markers:
        flags.append("page_markers_removed")
    context = f"{provision.title}\n{provision_label(provision.address)}\n{body}"
    return Chunk(
        chunk_id=f"{provision.document_id}|{provision.text_sha256}|{provision.address}|{md5(body)}|0",
        document_id=provision.document_id,
        text_sha256=provision.text_sha256,
        source_address=provision.address,
        address=provision.address,
        kind=provision.kind,
        label=provision.label,
        heading=provision.heading,
        title=provision.title,
        citation=provision.citation or provision.title,
        issuer=provision.issuer,
        doc_status=provision.status,
        valid_from=provision.valid_from,
        valid_to=provision.valid_to,
        body=body,
        context_text=context,
        token_count=len(context.split()),
        searchable=not any(flag in UNSEARCHABLE for flag in flags),
        flags=flags,
    )
