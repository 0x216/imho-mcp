"""Exceptions raised by the imho client."""

from __future__ import annotations

from typing import Optional


class ImhoError(Exception):
    """Any error answer from imho.run.

    ``code`` is the API's error code when it sent one (``not_found``,
    ``bad_request``, ``rate_limited``, ``disabled``), ``status`` the HTTP status.
    """

    def __init__(
        self,
        detail: str,
        *,
        code: Optional[str] = None,
        status: Optional[int] = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.status = status


class NotFoundError(ImhoError):
    """No game matched the query."""


class BadRequestError(ImhoError):
    """The request was rejected (a parameter out of range, an empty query)."""


class RateLimitError(ImhoError):
    """Too many requests. ``retry_after`` is in seconds when the server sent it."""

    def __init__(
        self,
        detail: str,
        *,
        code: Optional[str] = "rate_limited",
        status: Optional[int] = 429,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(detail, code=code, status=status)
        self.retry_after = retry_after


class DisabledError(ImhoError):
    """The API is switched off on the server side for now."""


class ToolError(ImhoError):
    """An MCP tool call returned ``isError: true``."""


__all__ = [
    "BadRequestError",
    "DisabledError",
    "ImhoError",
    "NotFoundError",
    "RateLimitError",
    "ToolError",
]
