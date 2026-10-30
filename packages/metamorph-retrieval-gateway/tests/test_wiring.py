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


def test_by_default_the_market_and_the_regulation_standin_are_joined() -> None:
    assert DEFAULT_PROVIDERS == ("metamorph_market_retrieval.wiring:market_provider,"
                                 "metamorph_regulation_standin.wiring:standin_provider")


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
