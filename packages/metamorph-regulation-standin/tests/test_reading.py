import pytest
from memory_regulations import MemoryRegulations
from standin_samples import ARTICLE_5_1, FATWA_117, POJK_40, RULING

from metamorph_regulation_standin.application.reading import Reading
from metamorph_regulation_standin.domain.evidence import document_evidence, unit_evidence
from metamorph_retrieval_contract.errors import UnknownRef
from metamorph_retrieval_contract.refs import Ref

R = Ref.parse


def reading() -> Reading:
    return Reading(MemoryRegulations())


def test_a_documents_ref_reads_the_document() -> None:
    assert reading().read(R("doc:ojk:pojk:2024:40")) == document_evidence(POJK_40)


def test_a_provisions_ref_reads_its_wording() -> None:
    assert reading().read(R("doc:ojk:pojk:2024:40#pasal-5/ayat-1")) == unit_evidence(ARTICLE_5_1)


@pytest.mark.parametrize(
    ("ref", "message"),
    [
        ("doc:ojk:pojk:2099:1", "doc:ojk:pojk:2099:1 isn't published"),
        ("doc:ojk:pojk:2024:40#pasal-99", "doc:ojk:pojk:2024:40 has no provision pasal-99 with wording of its own; "
                                          "read the document for its card"),
    ],
)
def test_what_isnt_published_is_an_unknown_ref_that_says_so(ref: str, message: str) -> None:
    with pytest.raises(UnknownRef, match=message):
        reading().read(R(ref))


def test_describe_answers_cards_in_the_order_asked_and_leaves_out_what_it_doesnt_hold() -> None:
    cards = reading().describe([R("doc:dsnmui:fatwa:117"), R("doc:ojk:pojk:2099:1"),
                                R("doc:dsnmui:fatwa:117#diktum-kedua/angka-1"), R("doc:ojk:pojk:2024:40")])

    assert cards == [document_evidence(FATWA_117).card(), unit_evidence(RULING).card(),
                     document_evidence(POJK_40).card()]


def test_describe_leaves_out_refs_in_other_namespaces() -> None:
    assert reading().describe([R("report:ojk:lpksi:2025")]) == []
