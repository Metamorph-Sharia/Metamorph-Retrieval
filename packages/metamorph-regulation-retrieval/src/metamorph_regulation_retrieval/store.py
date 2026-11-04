"""Query the regulation index: two rankings of its retrieval units, which the provider fuses.

- **By meaning:** candidates from the halfvec graph, then a full-precision rescore. The halfvec index is half the
  size of the float one and fits a 4 GiB instance; rescoring recovers the ranking that quantisation costs.
- **By words:** the question's stems, as the market provider matches them: any of them, but a unit must hold at
  least WORDS_SHARE of them, so one common word isn't a match. A term the question turns on ("escrow", "Rp5 miliar",
  a fatwa's number) is found even where its meaning is too close to many others.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

from metamorph_regulation_retrieval.domain.filters import NO_FILTERS, Filters
from metamorph_regulation_retrieval.domain.links import CHANGING, ORDER, LinkRow
from metamorph_regulation_retrieval.domain.passage import Passage
from metamorph_regulation_retrieval.indexing.build import links_table, stems_table
from metamorph_regulation_retrieval.indexing.chunks import LANGUAGE

CHUNK_TABLE = "METAMORPH_REGULATION_CHUNK_TABLE"
EMBED_TABLE = "METAMORPH_REGULATION_EMBED_TABLE"
META_TABLE = "METAMORPH_REGULATION_META_TABLE"

DEFAULT_CHUNK = "regulation_chunk_live"
DEFAULT_EMBED = "regulation_emb_live"
DEFAULT_META = "regulation_meta_live"

COLUMNS = """
c.chunk_id, c.document_id, c.address, c.title, c.citation, c.body,
m.kind, m.status, c.valid_from, c.valid_to, m.effective_on, m.promulgated_on,
m.published_at, c.issuer, m.family, m.number, m.year, m.citation as doc_citation
"""

BARE = """
chunk_id, document_id, address, title, citation, body,
kind, status, valid_from, valid_to, effective_on, promulgated_on,
published_at, issuer, family, number, year, doc_citation
"""

SEARCH = """
with candidates as (
  select {columns}, e.embedding as embedding
  from {embed} e
  join {chunk} c using (chunk_id)
  join {meta} m on m.document_id = c.document_id
  where c.searchable{where}
  order by (e.embedding::halfvec({dim})) <=> (%(vector)s::vector)::halfvec({dim})
  limit %(depth)s
)
select {bare}, 1 - (embedding <=> %(vector)s::vector) as score
from candidates
order by embedding <=> %(vector)s::vector
limit %(limit)s
"""

# What `in_force_on` keeps: documents in force that day, and their provisions not yet ended. A provision's valid_to is
# the day its wording stopped applying (published-schema.md), so it is excluded from that day on.
IN_FORCE = """
  and (m.effective_on is null or m.effective_on <= %(day)s)
  and (c.valid_to is null or c.valid_to > %(day)s)
  and not {revoked}"""
REVOKED_ON = "coalesce(m.revoked_on <= %(day)s, m.status = 'revoked')"
REVOKED_NOW = "m.status = 'revoked'"  # an index built before revocations were dated

# The question's stems a search can use are those some unit holds: a stem none holds can't match. Of those, only the
# uncommon pick candidates (the build counts them): a stem most units hold would make the search match nearly all of
# them, and score each. All of them count once a unit is a candidate: the share it holds, and its rank. The stems are
# matched as lexemes, as they are. ts_rank's normalisation 1 divides by 1 + log(length), so a long unit doesn't win on
# length alone.
WORDS = """
with asked as (
  select coalesce(array_agg(distinct s.word), '{{}}') as stems,
         coalesce(array_agg(distinct s.word) filter (where not s.common), '{{}}') as picking
  from unnest(tsvector_to_array(to_tsvector('{language}', %(query)s))) as q(word)
  join {stems} s on s.word = q.word
),
wanted as (
  select array_to_string(array(select quote_literal(word) from unnest(picking) as word), ' | ')::tsquery as picks,
         array_to_string(array(select quote_literal(word) from unnest(stems) as word), ' | ')::tsquery as query
  from asked where cardinality(picking) > 0
)
select {columns}, ts_rank(c.words, wanted.query, 1) as score
from {chunk} c
join {meta} m on m.document_id = c.document_id
cross join asked cross join wanted
where c.searchable and c.words @@ wanted.picks{where}
  and cardinality(array(select unnest(tsvector_to_array(c.words)) intersect select unnest(asked.stems)))
      >= %(share)s * cardinality(asked.stems)
order by score desc, c.chunk_id
limit %(limit)s
"""
WORDS_SHARE = 0.5  # the market's: a question is longer than what answers it, but one shared word isn't a match

READ = """
select {columns}
from {chunk} c
join {meta} m on m.document_id = c.document_id
where c.document_id = %s and c.address = %s
limit 1
"""

# to_jsonb, since an index built before status histories has no such column
DOCUMENT = """
select document_id, kind, citation, title, issuer, status, family, number, year,
       promulgated_on, effective_on, published_at, aliases, to_jsonb(m) -> 'status_history'
from {meta} m
where document_id = %s
"""

DOCUMENT_COLUMNS = (
    "document_id", "kind", "citation", "title", "issuer", "status", "family", "number",
    "year", "promulgated_on", "effective_on", "published_at", "aliases", "status_history",
)

# A document's links cross to other documents: those inside it are its provisions'. A provision's are those on it or on
# a part of it, and what changes what holds it.
LINKS = """
select type, from_document, from_address, to_document, to_address, effective_on, confidence
from {links}
where ({where}){types}
order by type = any(%(changing)s) and to_document = %(document)s desc, array_position(%(order)s::text[], type),
         effective_on desc nulls last, from_document, from_address nulls first, to_document, to_address nulls first
limit %(limit)s offset %(offset)s
"""

OTHER_DOCUMENTS = "from_document <> to_document"
WITHIN = "({end} = %(address)s or left({end}, length(%(address)s) + 1) = %(address)s || '/')"
HOLDING = ("(type = any(%(changing)s) and (to_address is null or left(%(address)s, length(to_address) + 1) "
           "= to_address || '/'))")


class PostgresStore:
    """The index database, read only."""

    def __init__(
        self,
        url: str,
        *,
        chunk_table: str | None = None,
        embed_table: str | None = None,
        meta_table: str | None = None,
        dimension: int = 1024,
        ef_search: int = 200,
        options: str | None = None,
    ) -> None:
        self.url = url
        self.options = options  # libpq options for each session, e.g. read only with a statement timeout
        self.chunk_table = _table(chunk_table or os.environ.get(CHUNK_TABLE, DEFAULT_CHUNK))
        self.embed_table = _table(embed_table or os.environ.get(EMBED_TABLE, DEFAULT_EMBED))
        self.meta_table = _table(meta_table or os.environ.get(META_TABLE, DEFAULT_META))
        self.dimension = dimension
        self.ef_search = ef_search
        self._columns: dict[tuple[str, str], bool] = {}
        self._iterative: bool | None = None

    def by_meaning(
        self, vector: Sequence[float], limit: int, filters: Filters = NO_FILTERS
    ) -> list[tuple[Passage, float]]:
        """The `limit` units nearest the question, among those the filters keep."""
        depth = max(int(limit) * 4, 50)
        where, parameters = self._where(filters)
        with self._connect() as conn:
            register_vector(conn)
            conn.execute(f"set local hnsw.ef_search = {max(self.ef_search, depth)}")
            if self._scans_iteratively(conn):
                # A filtered HNSW scan (the filters, and `searchable`) otherwise stops at ef_search candidates, most of
                # them filtered out. The outer query orders them exactly again.
                conn.execute("set local hnsw.iterative_scan = relaxed_order")
            rows = conn.execute(
                SEARCH.format(
                    columns=COLUMNS, bare=BARE, embed=self.embed_table, chunk=self.chunk_table,
                    meta=self.meta_table, dim=self.dimension, where=where,
                ),
                {"vector": list(vector), "depth": depth, "limit": limit, **parameters},
            ).fetchall()
        return [(_passage(row), float(row[18])) for row in rows]

    def by_words(self, query: str, limit: int, filters: Filters = NO_FILTERS) -> list[tuple[Passage, float]]:
        """The `limit` units sharing most of the question's words, among those the filters keep."""
        where, parameters = self._where(filters)
        with self._connect() as conn:
            rows = conn.execute(
                WORDS.format(columns=COLUMNS, chunk=self.chunk_table, meta=self.meta_table, where=where,
                             language=LANGUAGE, stems=stems_table(self.chunk_table)),
                {"query": query, "limit": limit, "share": WORDS_SHARE, **parameters},
            ).fetchall()
        return [(_passage(row), float(row[18])) for row in rows]

    def matches_words(self) -> bool:
        """Whether the index holds the units' words and their stems (indexes built since 2026-11-03)."""
        return self._has_column(self.chunk_table, "words") and self._has_column(stems_table(self.chunk_table), "common")

    def holds_links(self) -> bool:
        """Whether the index holds the links (indexes built since 2026-11-04)."""
        return self._has_column(links_table(self.chunk_table), "type")

    def links(self, document_id: str, address: str | None, *, incoming: bool, outgoing: bool, types: Sequence[str],
              limit: int, offset: int) -> list[LinkRow]:
        """The links asked for: what changes the text, then the rest (domain.links), the newest of each type first."""
        sides = [*([_incoming(address)] if incoming else []), *([_outgoing(address)] if outgoing else [])]
        query = LINKS.format(links=links_table(self.chunk_table), where=" or ".join(sides),
                             types=" and type = any(%(types)s)" if types else "")
        with self._connect() as conn:
            rows = conn.execute(query, {"document": document_id, "address": address, "changing": list(CHANGING),
                                        "types": list(types), "order": list(ORDER), "limit": limit,
                                        "offset": offset}).fetchall()
        return [LinkRow(*row) for row in rows]

    def dates_revocations(self) -> bool:
        """Whether the index knows when each revoked document was revoked (indexes built since 2026-11-03)."""
        return self._has_column(self.meta_table, "revoked_on")

    def _has_column(self, table: str, column: str) -> bool:
        if (table, column) not in self._columns:
            with self._connect() as conn:
                self._columns[(table, column)] = conn.execute(
                    "select count(*) from information_schema.columns "
                    "where table_schema = any(current_schemas(false)) and table_name = %s and column_name = %s",
                    (table, column),
                ).fetchone()[0] > 0
        return self._columns[(table, column)]

    def _where(self, filters: Filters) -> tuple[str, dict[str, Any]]:
        clauses, parameters = [], {}
        if filters.kinds:
            clauses.append("\n  and m.kind = any(%(kinds)s)")
            parameters["kinds"] = sorted(filters.kinds)
        if filters.issuers:
            clauses.append("\n  and c.issuer = any(%(issuers)s)")
            parameters["issuers"] = sorted(filters.issuers)
        if filters.documents:
            clauses.append("\n  and c.document_id = any(%(documents)s)")
            parameters["documents"] = list(filters.documents)
        if filters.in_force_on:
            clauses.append(IN_FORCE.format(revoked=REVOKED_ON if self.dates_revocations() else REVOKED_NOW))
            parameters["day"] = filters.in_force_on
        return "".join(clauses), parameters

    def _scans_iteratively(self, conn: psycopg.Connection) -> bool:
        """pgvector 0.8 and later can keep scanning the graph until enough candidates pass the filters."""
        if self._iterative is None:
            row = conn.execute("select extversion from pg_extension where extname = 'vector'").fetchone()
            self._iterative = bool(row) and tuple(int(part) for part in row[0].split(".")[:2]) >= (0, 8)
        return self._iterative

    def read(self, document_id: str, address: str) -> Passage | None:
        with self._connect() as conn:
            row = conn.execute(
                READ.format(columns=COLUMNS, chunk=self.chunk_table, meta=self.meta_table),
                (document_id, address),
            ).fetchone()
        return _passage(row) if row else None

    def document(self, document_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                DOCUMENT.format(meta=self.meta_table), (document_id,)
            ).fetchone()
        return dict(zip(DOCUMENT_COLUMNS, row, strict=True)) if row else None

    def published_at(self):
        with self._connect() as conn:
            return conn.execute(f"select max(published_at) from {self.meta_table}").fetchone()[0]

    def _connect(self, **settings: Any) -> psycopg.Connection:
        if self.options:
            settings = {"options": session_options(self.url, self.options), **settings}
        return psycopg.connect(self.url, **settings)

    def ping(self) -> None:
        with self._connect(connect_timeout=2) as conn:
            conn.execute(f"select 1 from {self.chunk_table} limit 1").fetchone()


def session_options(url: str, options: str, environ: Mapping[str, str] = os.environ) -> str:
    """The options every session takes, then these: PGOPTIONS, as libpq reads it, and the URL's own. Either can name
    the schema the index is in (`-c search_path=retrieval_regulation,public`). Options passed to a connection replace
    PGOPTIONS, so they are joined here instead."""
    named = [environ.get("PGOPTIONS", ""), psycopg.conninfo.conninfo_to_dict(url).get("options") or "", options]
    return " ".join(option for option in named if option)


def _passage(row: Sequence[Any]) -> Passage:
    return Passage(
        chunk_id=row[0],
        document_id=row[1],
        address=row[2],
        title=row[3],
        citation=row[4],
        text=row[5],
        doc_kind=row[6],
        doc_status=row[7],
        valid_from=row[8],
        valid_to=row[9],
        effective_on=row[10],
        promulgated_on=row[11],
        published_at=row[12],
        issuer=row[13],
        family=row[14],
        number=row[15],
        year=row[16],
        doc_citation=row[17],
    )


def _table(name: str) -> str:
    import re

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"{name!r} is not a table name")
    return name


def _incoming(address: str | None) -> str:
    if address is None:
        return f"to_document = %(document)s and {OTHER_DOCUMENTS}"
    return f"to_document = %(document)s and ({WITHIN.format(end='to_address')} or {HOLDING})"


def _outgoing(address: str | None) -> str:
    if address is None:
        return f"from_document = %(document)s and {OTHER_DOCUMENTS}"
    return f"from_document = %(document)s and {WITHIN.format(end='from_address')}"
