"""Retrieval contract 0.1: what crosses between a retrieval provider, the gateway and an answering agent.

See RETRIEVAL_CONTRACT.md. The JSON Schema in `schemas/retrieval.schema.json` is the formal contract.
"""

from metamorph_retrieval_contract.codec import ContractViolation, to_dict
from metamorph_retrieval_contract.conformance import Samples, ToolCall, conformance_problems
from metamorph_retrieval_contract.errors import (
    CapabilityMissing,
    InvalidArgument,
    ProviderUnavailable,
    RetrievalError,
    UnknownRef,
    UnknownTool,
)
from metamorph_retrieval_contract.evidence import (
    Body,
    EmptyReason,
    Evidence,
    Figures,
    Hit,
    LegalForce,
    MatchedBy,
    Observation,
    Page,
    PageSpan,
    Provenance,
    Qualifiers,
    Record,
    Text,
)
from metamorph_retrieval_contract.links import Direction, Link, LinkType
from metamorph_retrieval_contract.provider import CONTRACT_VERSION, JSON, Manifest, RetrievalProvider, ToolSpec
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import DEFAULT_LIMIT, MAX_LIMIT, LinksRequest, SearchRequest, Sort

__all__ = [
    "CONTRACT_VERSION",
    "DEFAULT_LIMIT",
    "JSON",
    "MAX_LIMIT",
    "Body",
    "CapabilityMissing",
    "ContractViolation",
    "Direction",
    "EmptyReason",
    "Evidence",
    "Figures",
    "Hit",
    "InvalidArgument",
    "LegalForce",
    "Link",
    "LinkType",
    "LinksRequest",
    "Manifest",
    "MatchedBy",
    "Observation",
    "Page",
    "PageSpan",
    "Provenance",
    "ProviderUnavailable",
    "Qualifiers",
    "Record",
    "Ref",
    "RetrievalError",
    "RetrievalProvider",
    "Samples",
    "SearchRequest",
    "Sort",
    "Text",
    "ToolCall",
    "ToolSpec",
    "UnknownRef",
    "UnknownTool",
    "conformance_problems",
    "to_dict",
]
