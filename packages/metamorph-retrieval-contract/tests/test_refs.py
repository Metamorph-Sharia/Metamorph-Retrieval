import pytest

from metamorph_retrieval_contract.errors import InvalidArgument
from metamorph_retrieval_contract.refs import Ref


def test_a_ref_reads_as_namespace_id_and_address() -> None:
    ref = Ref.parse("doc:ojk:pojk:2024:40#pasal-5/ayat-1")

    assert ref == Ref("doc", "ojk:pojk:2024:40", "pasal-5/ayat-1")
    assert str(ref) == "doc:ojk:pojk:2024:40#pasal-5/ayat-1"


def test_a_ref_without_an_address_names_the_whole() -> None:
    ref = Ref.parse("series:bi:seki:tabel1_1:monthly:row=1")

    assert ref == Ref("series", "bi:seki:tabel1_1:monthly:row=1")
    assert str(ref) == "series:bi:seki:tabel1_1:monthly:row=1"


def test_a_passage_knows_the_whole_it_belongs_to() -> None:
    assert Ref.parse("report:ojk:lpksi:2025#p-12").whole() == Ref("report", "ojk:lpksi:2025")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "ojk:pojk:2024:40#",  # an empty address
        "pojk",  # no namespace
        "Doc:ojk:pojk:2024:40",  # namespaces are lower case
        "doc:",  # no id
        "doc:ojk pojk",  # whitespace
        "doc:a#b#c",  # two addresses
    ],
)
def test_text_that_is_not_a_ref_is_refused_with_what_a_ref_looks_like(text: str) -> None:
    with pytest.raises(InvalidArgument, match="is not a ref, such as doc:ojk:pojk:2024:40#pasal-5"):
        Ref.parse(text)


def test_a_ref_built_in_code_is_checked_as_a_parsed_one_is() -> None:
    with pytest.raises(InvalidArgument):
        Ref("doc", "ojk pojk")
