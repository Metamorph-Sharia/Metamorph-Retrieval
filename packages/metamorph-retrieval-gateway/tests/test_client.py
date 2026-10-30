"""The gateway's client speaks the contract over HTTP, so anything that takes a provider (the evaluation runner, an
agent's own code) can take the gateway instead."""

import pytest
from fakes import POJK_40, SHARIA_LENDING, Industries, Regulations
from memory_provider import MemoryProvider
from retrieval_samples import regulation, release_passage, report_passage
from starlette.testclient import TestClient

from metamorph_retrieval_contract.conformance import Samples, ToolCall, conformance_problems
from metamorph_retrieval_contract.errors import ProviderUnavailable, UnknownRef
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_gateway.adapters.http import http_app
from metamorph_retrieval_gateway.application.catalog import Catalog
from metamorph_retrieval_gateway.application.gateway import Gateway
from metamorph_retrieval_gateway.client import GATEWAY_TOKEN, GATEWAY_URL, RetrievalClient, from_environment


def retrieval(*providers: object, **options: object) -> RetrievalClient:
    providers = providers or (MemoryProvider(), Regulations(), Industries())
    app = http_app(Catalog(Gateway(providers, **options)))  # type: ignore[arg-type]
    return RetrievalClient(TestClient(app))


def test_the_gateway_keeps_the_contract_over_http() -> None:
    samples = Samples(
        refs=(report_passage().ref, release_passage().ref, POJK_40, SHARIA_LENDING),
        unknown=Ref.parse("doc:ojk:pojk:1999:1"),
        query="fintech syariah ojk",
        linked=POJK_40,
        tool_calls=(ToolCall("count", {"kind": "report"}), ToolCall("industry_context", {})),
    )

    assert conformance_problems(retrieval(), samples) == []


def test_reading_returns_the_evidence() -> None:
    assert retrieval().read(POJK_40) == regulation()


def test_an_error_is_raised_as_its_type() -> None:
    with pytest.raises(UnknownRef, match="regulation holds nothing under doc:ojk:pojk:1999:1"):
        retrieval().read(Ref.parse("doc:ojk:pojk:1999:1"))
    with pytest.raises(ProviderUnavailable, match="industries didn't answer"):
        retrieval(Industries(delay=0.5), timeout=0.05).call("industry_context", {})


def test_a_token_from_the_environment_goes_with_every_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GATEWAY_URL, "https://gateway.example")
    monkeypatch.setenv(GATEWAY_TOKEN, "a-token")
    assert from_environment().http.headers["authorization"] == "Bearer a-token"


def test_without_a_token_no_authorization_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(GATEWAY_URL, "http://localhost:8765")
    monkeypatch.delenv(GATEWAY_TOKEN, raising=False)
    assert "authorization" not in from_environment().http.headers
