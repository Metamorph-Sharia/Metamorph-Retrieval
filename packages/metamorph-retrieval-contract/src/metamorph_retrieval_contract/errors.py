"""The errors a provider or the gateway may raise. Each has a code an agent can act on, and a message it can read.

"Nothing found" is never an error: it is an empty page with its reason (`Page.empty`).
"""

from __future__ import annotations


class RetrievalError(Exception):
    code = "retrieval_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnknownRef(RetrievalError):
    """No provider holds this ref: it is well formed, but nothing is published under it."""

    code = "unknown_ref"


class UnknownTool(RetrievalError):
    code = "unknown_tool"


class InvalidArgument(RetrievalError):
    """An argument the caller can fix: a malformed ref, an empty query, dates in the wrong order, a limit over the
    maximum. The message says what would be accepted."""

    code = "invalid_argument"


class CapabilityMissing(RetrievalError):
    """The provider doesn't offer this operation; its manifest says which it offers."""

    code = "capability_missing"


class ProviderUnavailable(RetrievalError):
    """The provider failed or didn't answer in time. Worth retrying later; the other providers may still answer."""

    code = "provider_unavailable"


ERRORS = {
    error.code: error
    for error in (UnknownRef, UnknownTool, InvalidArgument, CapabilityMissing, ProviderUnavailable)
}
