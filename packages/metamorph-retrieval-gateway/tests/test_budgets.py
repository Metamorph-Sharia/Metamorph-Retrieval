import pytest
from fakes import POJK_40, SHARIA_LENDING, Industries, Regulations

from metamorph_retrieval_contract.errors import ProviderUnavailable, UnknownRef
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_gateway.application.gateway import Gateway


def test_a_provider_slower_than_the_timeout_is_unavailable_and_the_message_says_so() -> None:
    slow = Gateway([Industries(delay=0.5), Regulations()], timeout=0.05)

    with pytest.raises(ProviderUnavailable, match=r"industries didn't answer within 0.05 s; try again later"):
        slow.call("industry_context", {})
    assert slow.read(POJK_40).ref == POJK_40  # the others still answer


def test_a_provider_that_crashes_is_unavailable_without_its_internals() -> None:
    broken = Gateway([Industries(fails=RuntimeError("connection to server lost: password=secret"))])

    with pytest.raises(ProviderUnavailable) as caught:
        broken.read(SHARIA_LENDING)

    assert caught.value.message == "industries failed (RuntimeError); try again later"


def test_a_providers_own_errors_reach_the_caller_as_they_are() -> None:
    with pytest.raises(UnknownRef, match="industries holds nothing under industry:ojk:portal:bank-umum-syariah"):
        Gateway([Industries()]).read(Ref.parse("industry:ojk:portal:bank-umum-syariah"))
