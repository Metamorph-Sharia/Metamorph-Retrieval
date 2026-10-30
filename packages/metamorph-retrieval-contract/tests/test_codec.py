import json
from datetime import date

import pytest
from retrieval_samples import company, m2_series, regulation, release_passage, report_passage
from test_provider import market_manifest

from metamorph_retrieval_contract import codec
from metamorph_retrieval_contract.codec import ContractViolation
from metamorph_retrieval_contract.errors import ERRORS, UnknownRef
from metamorph_retrieval_contract.evidence import EmptyReason, Evidence, Hit, LegalForce, MatchedBy, Page
from metamorph_retrieval_contract.links import Direction, Link, LinkType
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest, SearchRequest, Sort

EVERY_BODY = [release_passage(), report_passage(), m2_series(), company(), regulation()]


def through_json(data: dict) -> dict:
    """What the other side reads: the dict as JSON text and back."""
    return json.loads(json.dumps(data, ensure_ascii=False, allow_nan=False))


@pytest.mark.parametrize("evidence", EVERY_BODY, ids=lambda evidence: evidence.kind)
def test_evidence_of_every_body_reads_back_as_written(evidence: Evidence) -> None:
    assert codec.evidence_from_dict(through_json(codec.to_dict(evidence))) == evidence


def test_a_card_reads_back_without_a_body() -> None:
    card = report_passage().card()

    assert codec.evidence_from_dict(through_json(codec.to_dict(card))) == card


def test_a_page_of_hits_reads_back_as_written() -> None:
    page = Page(
        items=(
            Hit(report_passage(), rank=1, score=0.031, matched_by=frozenset({MatchedBy.SEMANTIC, MatchedBy.WORDS})),
            Hit(release_passage(), rank=2, score=0.016, matched_by=frozenset({MatchedBy.WORDS})),
        ),
        cursor="b2Zmc2V0PTI",
        warnings=("issuers: reports are filtered by issuer; releases are all OJK's",),
    )

    assert codec.hits_from_dict(through_json(codec.to_dict(page))) == page


def test_an_empty_page_reads_back_with_its_reason() -> None:
    page = Page.empty(EmptyReason.NO_MATCH)

    assert codec.hits_from_dict(through_json(codec.to_dict(page))) == page
    assert codec.links_from_dict(through_json(codec.to_dict(page))) == page


def test_a_page_of_links_reads_back_as_written() -> None:
    page = Page(items=(
        Link(LinkType.NAMES, Ref.parse("release:ojk:siaran-pers:2025:x#p-2"), Ref.parse("doc:ojk:pojk:2024:40")),
        Link(LinkType.AMENDS, Ref.parse("doc:ojk:pojk:2025:3"), Ref.parse("doc:ojk:pojk:2024:40"),
             effective_on=date(2025, 3, 1), confidence=0.97),
    ))

    assert codec.links_from_dict(through_json(codec.to_dict(page))) == page


def test_a_search_needs_only_its_query_and_reads_the_rest_as_defaults() -> None:
    assert codec.search_request_from_dict({"query": "persyaratan perizinan"}) == SearchRequest("persyaratan perizinan")


def test_a_search_with_every_filter_reads_back_as_written() -> None:
    request = SearchRequest(
        "arah pengembangan",
        kinds=frozenset({"report"}),
        issuers=frozenset({"ojk"}),
        documents=(Ref.parse("doc:ojk:pojk:2024:40"),),
        published_from=date(2025, 1, 1),
        published_to=date(2026, 10, 30),
        in_force_on=date(2026, 10, 30),
        legal_force=frozenset({LegalForce.NONE}),
        sort=Sort.NEWEST,
        limit=25,
        cursor="b2Zmc2V0PTI",
    )

    assert codec.search_request_from_dict(through_json(codec.to_dict(request))) == request


def test_a_links_request_reads_back_as_written() -> None:
    request = LinksRequest(Direction.INCOMING, frozenset({LinkType.NAMES, LinkType.AMENDS}), limit=3)

    assert codec.links_request_from_dict(through_json(codec.to_dict(request))) == request
    assert codec.links_request_from_dict({}) == LinksRequest()


def test_a_manifest_reads_back_as_written() -> None:
    manifest = market_manifest()

    assert codec.manifest_from_dict(through_json(codec.to_dict(manifest))) == manifest


@pytest.mark.parametrize("code", sorted(ERRORS))
def test_an_error_reads_back_as_its_own_type(code: str) -> None:
    error = ERRORS[code]("no published document has the ref doc:ojk:pojk:2099:1")

    read = codec.error_from_dict(through_json(codec.to_dict(error)))

    assert (type(read), read.message) == (type(error), error.message)


def test_an_error_is_its_code_and_message() -> None:
    assert codec.to_dict(UnknownRef("no such ref")) == {"error": "unknown_ref", "message": "no such ref"}


def test_reading_lists_every_way_the_data_breaks_the_contract() -> None:
    data = codec.to_dict(report_passage())
    data["legal_force"] = "advisory"
    data["published_on"] = "20 Mei 2026"

    with pytest.raises(ContractViolation) as caught:
        codec.evidence_from_dict(data)

    assert [problem.split(":")[0] for problem in caught.value.problems] == ["legal_force", "published_on"]


def test_a_search_over_the_limit_or_with_unknown_fields_is_refused() -> None:
    with pytest.raises(ContractViolation, match="limit: 26 is greater than the maximum of 25"):
        codec.search_request_from_dict({"query": "pembiayaan", "limit": 26})
    with pytest.raises(ContractViolation, match="'top_k' was unexpected"):
        codec.search_request_from_dict({"query": "pembiayaan", "top_k": 5})


def test_what_the_schema_allows_but_the_types_refuse_is_a_violation_too() -> None:
    with pytest.raises(ContractViolation, match="an empty page says why"):
        codec.hits_from_dict({"items": [], "cursor": None, "empty_reason": None, "warnings": []})
    with pytest.raises(ContractViolation, match="query: say what to search for"):
        codec.search_request_from_dict({"query": "   "})


def test_a_page_of_evidence_reads_back_as_written() -> None:
    page = Page(items=(company(), m2_series()), cursor="b2Zmc2V0PTI")

    assert codec.evidence_page_from_dict(through_json(codec.to_dict(page))) == page
    assert codec.evidence_page_from_dict(through_json(codec.to_dict(Page.empty(EmptyReason.NO_MATCH)))) == Page.empty(
        EmptyReason.NO_MATCH
    )
