from datetime import UTC, datetime

import pytest
from fakes import Industries, Recorded, Regulations

from metamorph_retrieval_gateway.application.calls import AllCallLogs, Call
from metamorph_retrieval_gateway.wiring import DEFAULT_PROVIDERS, catalog_from, providers_from


def test_providers_are_named_by_their_factories() -> None:
    found = providers_from("fakes:regulations, fakes:industries")

    assert [type(provider) for provider in found] == [Regulations, Industries]


@pytest.mark.parametrize(
    ("named", "message"),
    [
        ("fakes", "fakes: name a factory as module:function, e.g. metamorph_market_retrieval.wiring:market_provider"),
        ("fakes:nowhere", "fakes:nowhere: fakes has no nowhere"),
        ("no_such_module:factory", "no_such_module:factory: no module named no_such_module"),
        ("fakes:NOT_A_FACTORY", "fakes:NOT_A_FACTORY: not a function"),
        (" , ", "name at least one provider"),
    ],
)
def test_a_factory_that_cant_be_found_says_why(named: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        providers_from(named)


def test_by_default_the_market_and_the_regulation_provider_are_joined() -> None:
    assert DEFAULT_PROVIDERS == ("metamorph_market_retrieval.wiring:market_provider,"
                                 "metamorph_regulation_retrieval.wiring:regulation_provider")


def test_the_catalog_is_built_from_the_environment(tmp_path) -> None:  # noqa: ANN001
    catalog = catalog_from({"METAMORPH_RETRIEVAL_PROVIDERS": "fakes:regulations,fakes:industries",
                            "METAMORPH_RETRIEVAL_TIMEOUT": "2.5", "METAMORPH_RETRIEVAL_CALL_LOG": str(tmp_path)})

    catalog.run("industry_context", {})

    assert [tool.name for tool in catalog.tools()] == ["read", "industry_context"]
    assert catalog.provider.timeout == 2.5  # type: ignore[attr-defined]
    assert len(list(tmp_path.glob("calls-*.jsonl"))) == 1


def test_every_call_log_gets_each_call_even_when_one_fails() -> None:
    class Failing:
        def record(self, call: Call) -> None:
            raise OSError("disk full")

    kept = Recorded()
    call = Call("c1", "read", {}, None, datetime(2026, 10, 30, tzinfo=UTC), 1.0)
    AllCallLogs([Failing(), kept]).record(call)

    assert kept.calls == [call]


def test_without_a_reranker_named_none_is_built() -> None:
    from metamorph_retrieval_gateway.wiring import reranker_from

    assert reranker_from("") is None and reranker_from("  ") is None


def test_the_cross_encoder_scores_each_text_for_the_question() -> None:
    from metamorph_retrieval_gateway.adapters.reranker import CrossEncoderReranker

    class Encoder:
        def predict(self, pairs, batch_size, show_progress_bar):  # noqa: ANN001, ANN202
            return [len(text) for _, text in pairs]

    reranker = CrossEncoderReranker("any", encoder=Encoder())
    assert reranker.scores("q", ["ab", "abcd"]) == [2.0, 4.0] and reranker.scores("q", []) == []


def test_the_gateway_as_serve_builds_it_can_be_evaluated_in_process(monkeypatch) -> None:  # noqa: ANN001
    from metamorph_retrieval_gateway.wiring import gateway_from_environment

    monkeypatch.setenv("METAMORPH_RETRIEVAL_PROVIDERS", "fakes:regulations,fakes:industries")
    monkeypatch.delenv("METAMORPH_RETRIEVAL_RERANKER", raising=False)
    gateway = gateway_from_environment()

    assert sorted(gateway.providers) == ["industries", "regulation"] and gateway.reranker is None
    assert gateway.candidates == 50
    monkeypatch.setenv("METAMORPH_RETRIEVAL_RERANK_CANDIDATES", "25")
    assert gateway_from_environment().candidates == 25
