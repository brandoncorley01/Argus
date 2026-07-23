"""Request correlation id middleware (Phase 15).

Every HTTP request is assigned a correlation id: the caller-supplied
`X-Correlation-ID` header when present and non-blank, otherwise a freshly
generated UUID4. The id is echoed back on the response header and exposed
via `get_correlation_id()` through a contextvar so operational-log helpers
invoked deeper in the request (services, not just route handlers) can
attribute `OperationalEvent` rows to the request that triggered them without
threading the id through every function signature.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_HEADER = "X-Correlation-ID"

_correlation_id: ContextVar[str | None] = ContextVar("argus_correlation_id", default=None)


def get_correlation_id() -> str:
    """Return the correlation id for the current context.

    Returns the id set by `CorrelationIdMiddleware` for the in-flight HTTP
    request, or a freshly generated UUID4 when called outside any request
    context (e.g. an ARQ worker cycle, which generates and threads its own
    id explicitly instead of relying on this contextvar).
    """
    value = _correlation_id.get()
    if value:
        return value
    return str(uuid.uuid4())


def set_correlation_id(value: str) -> None:
    """Explicitly set the correlation id for the current context (non-HTTP callers)."""
    _correlation_id.set(value)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Ensures every request carries a stable correlation id end-to-end."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(CORRELATION_HEADER)
        correlation_id = incoming.strip() if incoming and incoming.strip() else str(uuid.uuid4())
        token = _correlation_id.set(correlation_id)
        try:
            response = await call_next(request)
        finally:
            _correlation_id.reset(token)
        response.headers[CORRELATION_HEADER] = correlation_id
        return response
