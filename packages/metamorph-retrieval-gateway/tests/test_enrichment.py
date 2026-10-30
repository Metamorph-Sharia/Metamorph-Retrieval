"""What a record names, the gateway cites: one batched describe to each owner, so a market answer carries the
citation and legal force of the regulations it names without the market provider ever reading them."""

from dataclasses import replace

from fakes import POJK_40, SHARIA_LENDING, UNPUBLISHED, Industries, Regulations, industry

from metamorph_retrieval_contract.evidence import Record
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.schema import schema_problems
from metamorph_retrieval_gateway.application.gateway import Gateway

CITED = {
    "ref": str(POJK_40),
    "kind": "regulation",
    "citation": "Peraturan Otoritas Jasa Keuangan Nomor 40 Tahun 2024",
    "title": "Layanan Pendanaan Bersama Berbasis Teknologi Informasi",
    "legal_force": "binding",
    "status": "in_force",
}


def named(output: dict) -> list[dict]:
    return output["items"][0]["body"]["fields"]["governed_by"]


def test_the_refs_a_tools_records_name_get_their_owners_citations() -> None:
    output = Gateway([Industries(), Regulations()]).call("industry_context", {})

    assert named(output) == [CITED, {"ref": str(UNPUBLISHED)}]  # not published yet: it stays a bare ref
    assert output["warnings"] == []


def test_a_record_read_is_cited_the_same_way() -> None:
    evidence = Gateway([Industries(), Regulations()]).read(SHARIA_LENDING)

    assert isinstance(evidence.body, Record)
    assert evidence.body.fields["governed_by"] == [CITED, {"ref": str(UNPUBLISHED)}]


def test_each_owner_is_asked_once_per_answer() -> None:
    regulations = Regulations()

    Gateway([Industries(industry(named=[POJK_40, UNPUBLISHED, POJK_40])), regulations]).call("industry_context", {})

    assert regulations.described == [[POJK_40, UNPUBLISHED]]


def test_what_a_stub_already_says_is_kept() -> None:
    evidence = industry()
    fields = {"governed_by": [{"ref": str(POJK_40), "citation": "POJK 40/2024", "role": "main"}]}
    output = Gateway([Industries(replace(evidence, body=Record(fields))), Regulations()]).call("industry_context", {})

    assert named(output) == [CITED | {"citation": "POJK 40/2024", "role": "main"}]


def test_refs_no_provider_owns_stay_bare() -> None:
    fatwa = Ref.parse("fatwa:dsnmui:117")
    output = Gateway([Industries(industry(named=[fatwa])), Regulations()]).call("industry_context", {})

    assert (named(output), output["warnings"]) == ([{"ref": str(fatwa)}], [])


def test_an_owner_that_doesnt_answer_leaves_the_refs_bare_and_says_so() -> None:
    output = Gateway([Industries(), Regulations(delay=0.5)], timeout=0.05).call("industry_context", {})

    assert named(output) == [{"ref": str(POJK_40)}, {"ref": str(UNPUBLISHED)}]
    assert output["warnings"] == ["named refs without citations: regulation didn't answer within 0.05 s; try again "
                                  "later"]


def test_past_the_budget_named_refs_stay_bare_and_the_page_says_how_many() -> None:
    many = [Ref.parse(f"doc:ojk:pojk:2099:{number}") for number in range(1, 46)]
    output = Gateway([Industries(industry(named=[POJK_40, *many])), Regulations()]).call("industry_context", {})

    assert named(output)[0] == CITED
    assert output["warnings"] == ["6 named refs left without citations, past the 40 cited in one answer; read them "
                                  "for theirs"]


def test_a_cited_answer_still_meets_the_contract() -> None:
    output = Gateway([Industries(), Regulations()]).call("industry_context", {})

    assert schema_problems(output, "evidence_page") == []


def test_refs_the_answering_provider_owns_are_left_as_it_named_them() -> None:
    regulations = Regulations()
    own = SHARIA_LENDING  # held by the industries provider, so describing it would cite it
    output = Gateway([Industries(industry(named=[own, POJK_40])), regulations]).call("industry_context", {})

    assert named(output) == [{"ref": str(own)}, CITED]
    assert regulations.described == [[POJK_40]]
