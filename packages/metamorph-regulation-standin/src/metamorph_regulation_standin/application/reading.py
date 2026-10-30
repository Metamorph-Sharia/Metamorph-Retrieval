"""Reading and describing `doc:` refs: a document's ref reads its card and facts, a provision's ref its wording.

The stand-in reads only what the read contract publishes. Search, outlines and the links between regulations are
the regulatory provider's, when it arrives.
"""

from __future__ import annotations

from collections.abc import Sequence

from metamorph_regulation_standin.application.ports import RegulationReadModel
from metamorph_regulation_standin.domain.evidence import NAMESPACE, document_evidence, unit_evidence
from metamorph_retrieval_contract.errors import UnknownRef
from metamorph_retrieval_contract.evidence import Evidence
from metamorph_retrieval_contract.refs import Ref


class Reading:
    def __init__(self, read_model: RegulationReadModel) -> None:
        self.read_model = read_model

    def read(self, ref: Ref) -> Evidence:
        found = self.describe([ref], cards=False)
        if found:
            return found[0]
        if ref.address is not None and self.read_model.documents([ref.id]):
            raise UnknownRef(f"{ref.whole()} has no provision {ref.address} with wording of its own; read the "
                             "document for its card")
        raise UnknownRef(f"{ref.whole()} isn't published")

    def describe(self, refs: Sequence[Ref], *, cards: bool = True) -> list[Evidence]:
        owned = [ref for ref in refs if ref.namespace == NAMESPACE]
        documents = {document.id: document
                     for document in self.read_model.documents([ref.id for ref in owned if ref.address is None])}
        units = {(unit.document.id, unit.address): unit
                 for unit in self.read_model.units([(ref.id, ref.address) for ref in owned if ref.address])}

        def held(ref: Ref) -> Evidence | None:
            if ref.address is None:
                return document_evidence(documents[ref.id]) if ref.id in documents else None
            unit = units.get((ref.id, ref.address))
            return unit_evidence(unit) if unit else None

        found = [evidence for evidence in map(held, owned) if evidence is not None]
        return [evidence.card() for evidence in found] if cards else found
