"""Searching report and release passages: full text and meaning, fused by rank, within explicit filters."""

from datetime import date

from market_samples import REVOKED, TARGETS
from memory_index import ConceptEmbedder, MemoryIndex
from memory_market import AFTER_TARGETS, BEFORE_TARGETS, MemoryMarket

from metamorph_market_retrieval.application.search import Meaning, SearchPassages
from metamorph_market_retrieval.domain.indexing import passage_unit
from metamorph_retrieval_contract.evidence import EmptyReason, LegalForce, MatchedBy
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import SearchRequest, Sort

PASSAGES = (BEFORE_TARGETS, TARGETS, AFTER_TARGETS, REVOKED)
FLOOR = 0.3


def search(query: str, *, meaning: bool = True, passages=PASSAGES, **filters: object):  # noqa: ANN001, ANN201
    embedder = ConceptEmbedder() if meaning else None
    index = MemoryIndex([passage_unit(passage) for passage in passages], embedder)
    meaning_of = Meaning(index, embedder, min_similarity=FLOOR) if embedder else None
    use_case = SearchPassages(MemoryMarket(), index, meaning_of)
    return use_case.run(SearchRequest(query, **filters))  # type: ignore[arg-type]


def refs(page) -> list[str]:  # noqa: ANN001
    return [str(hit.evidence.ref) for hit in page.items]


def test_a_passage_both_rankings_find_comes_first_and_says_how_it_matched() -> None:
    page = search("pembiayaan sektor produktif")

    assert refs(page)[0] == "report:ojk:roadmap:2023:lpbbti#p-43"
    assert page.items[0].matched_by == {MatchedBy.WORDS, MatchedBy.SEMANTIC}
    assert [hit.rank for hit in page.items] == list(range(1, len(page.items) + 1))


def test_meaning_finds_what_shares_no_word_with_the_question() -> None:
    page = search("productive sector financing")

    assert refs(page)[0] == "report:ojk:roadmap:2023:lpbbti#p-43"
    assert page.items[0].matched_by == {MatchedBy.SEMANTIC}


def test_a_question_nothing_speaks_to_is_no_match_rather_than_the_nearest_passages() -> None:
    page = search("resep rendang padang")

    assert (page.items, page.empty_reason) == ((), EmptyReason.NO_MATCH)


def test_without_an_embedder_search_is_full_text_alone() -> None:
    page = search("izin usaha", meaning=False)

    assert refs(page) == ["release:ojk:siaran-pers:2024:ojk-cabut-izin-usaha-pt-investree-radhika-jaya#p-1"]
    assert page.items[0].matched_by == {MatchedBy.WORDS}


RELEASE = "release:ojk:siaran-pers:2024:ojk-cabut-izin-usaha-pt-investree-radhika-jaya#p-1"
ROADMAP = "report:ojk:roadmap:2023:lpbbti"
BROAD = "pembiayaan produktif izin usaha"


def test_kinds_keep_only_those_kinds() -> None:
    assert refs(search(BROAD, kinds=frozenset({"release"}))) == [RELEASE]


def test_documents_keep_only_those_documents_passages() -> None:
    found = refs(search(BROAD, documents=(Ref.parse(ROADMAP),)))

    assert found and all(ref.startswith(f"{ROADMAP}#") for ref in found)


def test_published_dates_keep_only_what_was_published_between_them() -> None:
    assert refs(search(BROAD, published_from=date(2024, 1, 1))) == [RELEASE]


def test_issuers_compare_without_case() -> None:
    assert refs(search(BROAD, issuers=frozenset({"ojk"}))) == refs(search(BROAD))
    assert search(BROAD, issuers=frozenset({"bi"})).empty_reason is EmptyReason.FILTERS_EXCLUDE_ALL


def test_filters_that_exclude_every_match_say_so_rather_than_no_match() -> None:
    page = search("pembiayaan produktif", published_from=date(2027, 1, 1))

    assert (page.items, page.empty_reason) == ((), EmptyReason.FILTERS_EXCLUDE_ALL)


def test_asking_for_binding_evidence_excludes_every_market_passage_and_says_why() -> None:
    page = search("pembiayaan produktif", legal_force=frozenset({LegalForce.BINDING}))

    assert page.empty_reason is EmptyReason.FILTERS_EXCLUDE_ALL
    assert page.warnings == ("legal_force: report and release passages are none; search the regulations for "
                             "binding evidence",)


def test_a_filter_market_passages_dont_have_is_noted_and_left_out() -> None:
    page = search("pembiayaan produktif", in_force_on=date(2026, 1, 1))

    assert page.items
    assert page.warnings == ("in_force_on: applies to regulations; report and release passages were kept as "
                             "published",)


def test_newest_puts_the_latest_published_first_among_matches() -> None:
    page = search("pembiayaan izin usaha", sort=Sort.NEWEST)

    assert refs(page)[0].startswith("release:")  # 2024, after the 2023 roadmap


def test_a_page_at_a_time() -> None:
    first = search("roadmap otoritas jasa keuangan", limit=2)  # the roadmap's three passages, and the release
    rest = search("roadmap otoritas jasa keuangan", limit=2, cursor=first.cursor)

    assert (len(first.items), first.cursor) == (2, "2")
    assert set(refs(first)).isdisjoint(refs(rest))
    assert [hit.rank for hit in rest.items] == [3, 4]


def test_each_hit_names_the_index_version_that_found_it() -> None:
    hit = search("pembiayaan produktif").items[0]

    assert hit.evidence.provenance.index_version == "market-test.1"
    assert hit.evidence.legal_force is LegalForce.NONE


def test_a_unit_no_longer_published_is_left_out_and_noted() -> None:
    gone = passage_unit(TARGETS)
    index = MemoryIndex([gone, passage_unit(REVOKED)], ConceptEmbedder())
    market = MemoryMarket()
    market.all_passages = [REVOKED]

    page = SearchPassages(market, index, Meaning(index, ConceptEmbedder(), min_similarity=FLOOR)).run(
        SearchRequest("pembiayaan produktif izin usaha"))

    assert refs(page) == ["release:ojk:siaran-pers:2024:ojk-cabut-izin-usaha-pt-investree-radhika-jaya#p-1"]
    assert page.warnings == ("1 found in the index is no longer published; the index is older than the data",)
