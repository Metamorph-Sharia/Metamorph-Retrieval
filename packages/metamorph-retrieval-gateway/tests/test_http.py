"""The catalog over HTTP, for tests and for clients without MCP; the same app serves MCP at /mcp."""

import pytest
from fakes import POJK_40, Industries, Recorded, Regulations
from memory_provider import MemoryProvider
from retrieval_samples import regulation
from starlette.testclient import TestClient

from metamorph_retrieval_contract import codec
from metamorph_retrieval_gateway.adapters.http import http_app
from metamorph_retrieval_gateway.application.calls import TraceContext
from metamorph_retrieval_gateway.application.catalog import Catalog
from metamorph_retrieval_gateway.application.gateway import Gateway


def client(*providers: object, log: Recorded | None = None, **options: object) -> TestClient:
    providers = providers or (MemoryProvider(), Regulations(), Industries())
    return TestClient(http_app(Catalog(Gateway(providers, **options), calls=log)))  # type: ignore[arg-type]


def test_it_answers_whether_it_is_up() -> None:
    assert client().get("/health").json() == {"status": "ok"}


def test_the_tools_are_listed_with_inlined_schemas() -> None:
    tools = client().get("/tools").json()

    assert [tool["name"] for tool in tools] == ["search_documents", "read", "follow_links", "count",
                                                "industry_context"]
    assert tools[1]["input_schema"]["required"] == ["ref"]


def test_a_tool_is_called_by_posting_its_arguments() -> None:
    response = client().post("/tools/read", json={"ref": str(POJK_40)})

    assert (response.status_code, response.json()) == (200, codec.to_dict(regulation()))


@pytest.mark.parametrize(
    ("path", "body", "status", "code"),
    [
        ("/tools/read", {"ref": "doc:ojk:pojk:1999:1"}, 404, "unknown_ref"),
        ("/tools/get_provision", {}, 404, "unknown_tool"),
        ("/tools/read", {"window": 1}, 400, "invalid_argument"),
        ("/tools/search_documents", {"query": "x", "kinds": ["fatwa"]}, 501, "capability_missing"),
    ],
)
def test_an_error_carries_the_contracts_code_and_an_http_status(path: str, body: dict, status: int,
                                                                  code: str) -> None:
    response = client().post(path, json=body)

    assert (response.status_code, response.json()["error"]) == (status, code)


def test_a_provider_that_is_late_is_a_503() -> None:
    response = client(Industries(delay=0.5), timeout=0.05).post("/tools/industry_context", json={})

    assert (response.status_code, response.json()["error"]) == (503, "provider_unavailable")


def test_a_body_that_isnt_a_json_object_is_an_invalid_argument() -> None:
    response = client().post("/tools/read", content=b"[1, 2")

    assert (response.status_code, response.json()) == (400, {"error": "invalid_argument",
                                                             "message": "the body must be a JSON object"})


def test_describe_answers_the_cards_held() -> None:
    response = client().post("/describe", json={"refs": [str(POJK_40), "doc:ojk:pojk:1999:1"]})

    assert response.json() == {"items": [codec.to_dict(regulation().card())]}


def test_the_traceparent_header_reaches_the_call_log() -> None:
    log = Recorded()

    client(log=log).post("/tools/count", json={"kind": "report"},
                         headers={"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"})

    assert log.calls[0].trace == TraceContext("4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7")


def test_openapi_describes_each_tool_as_a_post() -> None:
    document = client().get("/openapi.json").json()

    assert document["openapi"].startswith("3.1")
    read = document["paths"]["/tools/read"]["post"]
    assert read["requestBody"]["content"]["application/json"]["schema"]["required"] == ["ref"]
    assert set(read["responses"]) == {"200", "400", "404", "501", "503"}
