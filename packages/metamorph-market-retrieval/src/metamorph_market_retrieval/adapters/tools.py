"""The market's own tools, as an agent sees them: a name, a description, and JSON Schemas in and out.

For an agent, the description is all it reads: each says what the tool is for, when to use it, what comes back, and
that market evidence never binds. Arguments are checked against the input schema before they are read, so an agent
is told every problem at once; the output schemas are the contract's own pages.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from metamorph_market_retrieval.application.companies import BUSINESS_TYPES, STATUSES, CompanyQuery, FindCompanies
from metamorph_market_retrieval.application.context import ContextQuery, IndustryContext
from metamorph_market_retrieval.application.ports import MarketReadModel
from metamorph_market_retrieval.application.search import Meaning
from metamorph_market_retrieval.application.statistics import (
    FREQUENCIES,
    MAX_FIGURES,
    MAX_SERIES,
    FindSeries,
    GetObservations,
    ObservationsQuery,
    SeriesQuery,
)
from metamorph_retrieval_contract.errors import InvalidArgument
from metamorph_retrieval_contract.evidence import Page
from metamorph_retrieval_contract.provider import JSON, ToolSpec
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import DEFAULT_LIMIT, MAX_LIMIT
from metamorph_retrieval_contract.schema import json_problems, load_schema

VERSION = "0.1"
PERIOD = {"type": "string", "pattern": r"^\d{4}(-(0[1-9]|1[0-2]|Q[1-4]|S[12]))?$",
          "description": "A month (2026-08), a quarter (2026-Q2), a half-year (2026-S1) or a year (2025)"}
LIMIT = {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": DEFAULT_LIMIT}
CURSOR = {"type": "string", "description": "The cursor of the page before, for the next page"}

FIND_COMPANIES = ToolSpec(
    name="find_companies",
    version=VERSION,
    description=(
        "Who OJK licenses, registers, or has dropped from a register (e.g. ojk:lpbbti, fintech lending), today or on a "
        "past date. Use it to list or count a market's players, to check one company by its legal or platform name, "
        "or to see what OJK announced about it. Without query, the companies filtered come by legal name; with query, "
        "companies come ranked by how well one of their names matches. With as_of, the register's edition current "
        "that day decides who was listed and their standing. Each company is evidence: its citation is the register's "
        "edition, qualifiers.status is licensed, registered or left, with its licences; with announcements, the "
        "release passages that name it, as refs to read. A listing is what a regulator lists, never a requirement: "
        "for what a licence requires, search the regulations."
    ),
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "register": {"type": "string", "description": "A register's id, e.g. ojk:lpbbti"},
            "query": {"type": "string", "minLength": 1, "description": "A legal or platform name, or part of one"},
            "status": {"enum": list(STATUSES)},
            "business_type": {"enum": list(BUSINESS_TYPES)},
            "as_of": {"type": "string", "format": "date", "description": "Standing on this day, e.g. 2020-06-30"},
            "announcements": {"type": "boolean", "default": False,
                              "description": "Also the release passages that name each company, newest first"},
            "limit": LIMIT,
            "cursor": CURSOR,
        },
    },
    output_schema={},  # set below, from the contract's pages
)

INDUSTRY_CONTEXT = ToolSpec(
    name="industry_context",
    version=VERSION,
    description=(
        "Start here for a question about an industry (sharia fintech lending, Bank Umum Syariah, BPR Syariah): the "
        "curated sector or industry, with its register, the regulations that govern it (doc refs), the regulators' "
        "reports on it and its datasets. Pass the doc refs to search_documents(documents=...) to search within those "
        "regulations, and the dataset refs to find_series. The links are curated by the Metamorph team, never "
        "inferred. Industries are matched by the words of their names, in Indonesian as the sources name them. A "
        "context is a map of where to look, never a requirement."
    ),
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["query"],
        "properties": {"query": {"type": "string", "minLength": 1}, "limit": LIMIT, "cursor": CURSOR},
    },
    output_schema={},
)

FIND_SERIES = ToolSpec(
    name="find_series",
    version=VERSION,
    description=(
        "Which statistics measure something, from OJK's portal (ojk:portal), BI's SEKI (bi:seki) and BPS's tables "
        "(bps:table). It looks for the tables first, then their series by label, so name the measure as the source "
        "would, in Indonesian: uang beredar, total aset bank umum syariah, inflasi tahunan. Series come ranked, each "
        "with its dataset, unit, frequency and first and last period; get their values with get_observations. A "
        "statistic is what a source counts, never a requirement."
    ),
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "minLength": 1},
            "source": {"type": "string", "description": "ojk:portal, bi:seki or bps:table"},
            "frequency": {"enum": list(FREQUENCIES)},
            "limit": LIMIT,
            "cursor": CURSOR,
        },
    },
    output_schema={},
)

GET_OBSERVATIONS = ToolSpec(
    name="get_observations",
    version=VERSION,
    description=(
        f"The figures of up to {MAX_SERIES} series between two periods, as the source gives them, never rescaled. "
        "Each series comes with its unit and frequency, its citation (quote it with the figure), its url and as_of "
        "(the source's last update); a figure the source marks provisional says so. Without from, only the newest "
        f"{MAX_FIGURES} figures of each. A figure is what a source counts, never a requirement."
    ),
    input_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["series"],
        "properties": {
            "series": {"type": "array", "minItems": 1, "maxItems": MAX_SERIES, "uniqueItems": True,
                       "items": {"type": "string", "pattern": "^series:[^\\s#]+$"},
                       "description": "Series refs, as find_series gives them"},
            "from": PERIOD,
            "to": PERIOD,
        },
    },
    output_schema={},
)


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    answer: Callable[[Mapping[str, Any]], Page[Any]]

    def run(self, arguments: Mapping[str, Any]) -> Page[Any]:
        problems = json_problems(dict(arguments), self.spec.input_schema)
        if problems:
            raise InvalidArgument(f"{self.spec.name}: {'; '.join(problems)}")
        return self.answer(arguments)


def market_tools(read_model: MarketReadModel, meaning: Meaning | None = None) -> dict[str, Tool]:
    find_companies, context = FindCompanies(read_model), IndustryContext(read_model, meaning=meaning)
    find_series, observations = FindSeries(read_model, meaning=meaning), GetObservations(read_model)
    tools = [
        Tool(_with_output(FIND_COMPANIES, "hit_page", "evidence_page"), lambda arguments: find_companies.run(
            CompanyQuery(**{**arguments, "as_of": _day(arguments.get("as_of"))}))),
        Tool(_with_output(INDUSTRY_CONTEXT, "hit_page"), lambda arguments: context.run(ContextQuery(**arguments))),
        Tool(_with_output(FIND_SERIES, "hit_page"), lambda arguments: find_series.run(SeriesQuery(**arguments))),
        Tool(_with_output(GET_OBSERVATIONS, "evidence_page"), lambda arguments: observations.run(ObservationsQuery(
            tuple(Ref.parse(ref) for ref in arguments["series"]), arguments.get("from"), arguments.get("to")))),
    ]
    return {tool.spec.name: tool for tool in tools}


def _with_output(spec: ToolSpec, *shapes: str) -> ToolSpec:
    contract = load_schema()
    pages: JSON = {"anyOf": [{"$ref": f"#/$defs/{shape}"} for shape in shapes]}  # an empty page fits either shape
    output = {"$schema": contract["$schema"], **pages, "$defs": contract["$defs"]}
    return ToolSpec(spec.name, spec.version, spec.description, spec.input_schema, output)


def _day(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
