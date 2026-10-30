"""The market's refs. Each is a published_market id under its namespace, so a ref survives any re-index.

An industry has no id of its own in the read contract: a statistics source names it. Its ref is the source and the
name as a slug, e.g. `industry:ojk:portal:bank-umum-syariah`.
"""

from __future__ import annotations

import re

from metamorph_retrieval_contract.refs import Ref

NAMESPACES = frozenset({"company", "register", "dataset", "series", "report", "release", "industry", "sector"})
NOT_A_WORD = re.compile(r"[^a-z0-9]+")


def slug(name: str) -> str:
    return NOT_A_WORD.sub("-", name.lower()).strip("-")


def industry_ref(source: str, name: str) -> Ref:
    return Ref("industry", f"{source}:{slug(name)}")


def doc_ref(regulation_id: str) -> Ref:
    """A regulation the market names: the regulation layer owns it."""
    return Ref("doc", regulation_id)
