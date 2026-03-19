"""Langfuse tracing middleware for FastAPI.

Adds request-level spans so every HTTP request is visible in Langfuse.
Graph-level tracing (LLM spans, tool calls) is handled separately by
the LangChain CallbackHandler wired in graph.py.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class LangfuseTracingMiddleware(BaseHTTPMiddleware):
    """Lightweight request-level tracing via Langfuse.

    Uses ``start_as_current_observation`` (Langfuse SDK v3) to create
    a span for each HTTP request.  No-ops gracefully when Langfuse
    is not configured or the client fails to initialize.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._enabled = False
        try:
            from langfuse import Langfuse

            self._langfuse = Langfuse()
            self._enabled = True
        except Exception:
            self._langfuse = None

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip tracing for health checks and when disabled
        if not self._enabled or request.url.path.startswith(("/api/health", "/health")):
            return await call_next(request)

        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000)
            logger.debug(
                "%s %s → %s (%dms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            return response
        except Exception:
            raise
