"""With a reranker, a search's candidates (each provider's first ones, fused) are put in the reranker's order, which
scores every candidate against the question on one scale, whichever provider found it."""

import time
from dataclasses import replace

import pytest
from fakes import POJK_40, Recorded, SearchingRegulations
from memory_provider import MemoryProvider
from retrieval_samples import regulation, release_passage, report_passage

from metamorph_retrieval_contract.errors import InvalidArgument
from metamorph_retrieval_contract.evidence import Record
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import SearchRequest
from metamorph_retrieval_gateway.application.catalog import Catalog
from metamorph_retrieval_gateway.application.gateway import Gateway
from metamorph_retrieval_gateway.application.reranking import NOT_RERANKED, rerank_text

QUESTION = "pembiayaan syariah izin usaha"


def regulations(count: int) -> list:
    return [replace(regulation(), ref=Ref.parse(f"doc:ojk:pojk:2024:{number}"), citation=f"POJK {number}/2024")
            for number in range(1, count + 1)]


class ByLength:
    """Scores the longer text higher: an order no provider gives, so a test sees the reranker's."""

    def __init__(self, *, fails: Exception | None = None, delay: float = 0.0) -> None:
        self.fails, self.delay = fails, delay
        self.asked: list[tuple[str, list[str]]] = []

    def scores(self, query: str, texts: list[str]) -> list[float]:
        self.asked.append((query, texts))
        time.sleep(self.delay)
        if self.fails:
            raise self.fails
        return [float(len(text)) for text in texts]


def refs(page) -> list[str]:  # noqa: ANN001 - a page of hits
    return [str(hit.evidence.ref) for hit in page.items]


def test_the_reranker_orders_every_providers_candidates_on_one_scale() -> None:
    reranker = ByLength()
    page = Gateway([MemoryProvider(), SearchingRegulations()], reranker=reranker).search(SearchRequest(QUESTION))

    texts = reranker.asked[0][1]
    assert reranker.asked[0][0] == QUESTION and len(texts) == 3
    assert [hit.score for hit in page.items] == sorted((float(len(text)) for text in texts), reverse=True)
    assert [hit.rank for hit in page.items] == [1, 2, 3]


def test_a_search_one_provider_holds_is_reranked_too() -> None:
    reranker = ByLength()
    page = Gateway([MemoryProvider(), SearchingRegulations()], reranker=reranker).search(
        SearchRequest(QUESTION, kinds=frozenset({"regulation"})))

    assert refs(page) == [str(POJK_40)] and len(reranker.asked) == 1


def test_candidates_come_from_each_providers_first_pages() -> None:
    searching = SearchingRegulations(regulations(60))
    Gateway([searching], reranker=ByLength(), candidates=50).search(SearchRequest("pendanaan", limit=5))

    assert [(request.limit, request.cursor) for request in searching.asked] == [(25, None), (25, "25")]


def test_the_reranked_order_pages_with_the_gateways_cursor() -> None:
    gateway = Gateway([SearchingRegulations(regulations(12))], reranker=ByLength())
    first = gateway.search(SearchRequest("pendanaan", limit=8))
    second = gateway.search(SearchRequest("pendanaan", limit=8, cursor=first.cursor))

    assert first.cursor == "fused:8" and second.cursor is None
    assert [hit.rank for hit in second.items] == [9, 10, 11, 12]
    assert not set(refs(first)) & set(refs(second))
    with pytest.raises(InvalidArgument):
        gateway.search(SearchRequest("pendanaan", cursor="8"))


def test_a_reranker_that_fails_leaves_the_fused_order_and_says_so() -> None:
    page = Gateway([MemoryProvider(), SearchingRegulations()], reranker=ByLength(fails=RuntimeError("boom"))).search(
        SearchRequest(QUESTION))

    assert len(page.items) == 3 and page.warnings == (NOT_RERANKED,)


def test_a_reranker_past_its_budget_leaves_the_fused_order() -> None:
    gateway = Gateway([MemoryProvider(), SearchingRegulations()], reranker=ByLength(delay=0.5), rerank_timeout=0.05)
    started = time.perf_counter()
    page = gateway.search(SearchRequest(QUESTION))

    assert page.warnings == (NOT_RERANKED,) and time.perf_counter() - started < 0.4


def test_the_text_reranked_is_what_a_reader_sees_first() -> None:
    assert rerank_text(regulation()) == ("Peraturan Otoritas Jasa Keuangan Nomor 40 Tahun 2024\n"
                                         "Layanan Pendanaan Bersama Berbasis Teknologi Informasi\n"
                                         "Peraturan Otoritas Jasa Keuangan ini mengatur…")
    record = replace(report_passage(), body=Record({"register": "ojk:lpbbti", "listed": 7, "named": [{"ref": "x"}]}))
    assert rerank_text(record).endswith("register: ojk:lpbbti\nlisted: 7")
    assert rerank_text(release_passage().card()).count("\n") == 1  # a card: its citation and title


def test_a_call_records_how_long_each_provider_and_the_reranker_took() -> None:
    log = Recorded()
    providers = [MemoryProvider(), SearchingRegulations()]
    catalog = Catalog(Gateway(providers, reranker=ByLength(delay=0.01)), calls=log)

    catalog.run("search_documents", {"query": QUESTION})

    stages = {stage.name: stage for stage in log.calls[0].stages}
    assert {provider.manifest().name for provider in providers} <= set(stages)
    assert stages["rerank"].duration_ms >= 10
