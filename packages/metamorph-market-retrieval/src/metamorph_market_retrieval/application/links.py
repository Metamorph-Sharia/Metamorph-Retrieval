"""links: which report and release passages name a regulation or a company, and what a passage names.

The market knows one kind of link, `names`: a passage's words name a regulation or a company. Whether it announced,
explained or merely cited it is in the words, which the agent reads. A regulation is the regulation layer's; the
market answers for the passages naming it all the same, and the gateway merges both layers' links.
"""

from __future__ import annotations

from metamorph_market_retrieval.application.paging import paged
from metamorph_market_retrieval.application.ports import MarketReadModel
from metamorph_market_retrieval.domain.records import Mention
from metamorph_market_retrieval.domain.refs import doc_ref
from metamorph_retrieval_contract.evidence import EmptyReason, Page
from metamorph_retrieval_contract.links import Direction, Link, LinkType
from metamorph_retrieval_contract.refs import Ref
from metamorph_retrieval_contract.requests import LinksRequest

NAMED_KINDS = {"doc": "regulation", "company": "company"}  # a ref's namespace → what a mention calls it
DOCUMENTS = ("report", "release")


class NamedBy:
    def __init__(self, read_model: MarketReadModel) -> None:
        self.read_model = read_model

    def run(self, ref: Ref, request: LinksRequest) -> Page[Link]:
        if request.types and LinkType.NAMES not in request.types:
            return Page.empty(EmptyReason.NO_MATCH)
        found: list[Link] = []
        if request.direction in (Direction.INCOMING, Direction.BOTH):
            found += self._naming(ref)
        if request.direction in (Direction.OUTGOING, Direction.BOTH):
            found += self._named_in(ref)
        return paged(found, request.limit, request.cursor, EmptyReason.NO_MATCH)

    def _naming(self, ref: Ref) -> list[Link]:
        if ref.address is not None or ref.namespace not in NAMED_KINDS:
            return []
        return [Link(LinkType.NAMES, _passage(mention), ref)
                for mention in self.read_model.mentions_of(NAMED_KINDS[ref.namespace], ref.id)]

    def _named_in(self, ref: Ref) -> list[Link]:
        if ref.namespace not in DOCUMENTS:
            return []
        return [Link(LinkType.NAMES, _passage(mention), _target(mention))
                for mention in self.read_model.mentions_in(ref.namespace, ref.id, ref.address)]


def _passage(mention: Mention) -> Ref:
    return Ref(mention.kind, mention.document, mention.address)


def _target(mention: Mention) -> Ref:
    return doc_ref(mention.target) if mention.target_kind == "regulation" else Ref("company", mention.target)
