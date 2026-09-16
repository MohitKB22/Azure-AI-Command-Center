"""Request ID propagation, access logging, security headers and rate limiting."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import correlation_id_ctx, get_logger, request_id_ctx

logger = get_logger("app.access")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request ID, propagate a correlation ID, log the outcome."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        correlation_id = request.headers.get("x-correlation-id") or request_id
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        request_token = request_id_ctx.set(request_id)
        correlation_token = correlation_id_ctx.set(correlation_id)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(request_token)
            correlation_id_ctx.reset(correlation_token)

        duration_ms = int((time.perf_counter() - started) * 1000)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if settings.environment != "local":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        if request.url.path not in {"/health/live", "/health/ready"}:
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "user": getattr(request.state, "user_email", None),
                },
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window in-process limiter.

    Adequate for a single API instance and for protecting local development.
    A multi-replica deployment should move this to Redis or to the ingress —
    see DEPLOYMENT.md.
    """

    EXEMPT_PATHS = {"/health/live", "/health/ready", "/openapi.json", "/docs", "/redoc"}

    def __init__(self, app, limit_per_minute: int | None = None):
        super().__init__(app)
        self.limit = limit_per_minute or settings.rate_limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _client_key(self, request: Request) -> str:
        api_key = request.headers.get("x-api-key")
        if api_key:
            return f"key:{api_key[:12]}"
        auth = request.headers.get("authorization", "")
        if auth:
            return f"jwt:{auth[-16:]}"
        return f"ip:{request.client.host if request.client else 'unknown'}"

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        key = self._client_key(request)
        now = time.time()
        with self._lock:
            window = self._hits[key]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self.limit:
                retry_after = int(60 - (now - window[0])) + 1
                logger.warning("rate_limited", extra={"path": request.url.path})
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limited",
                            "message": "Too many requests. Slow down and retry.",
                            "details": {"limit_per_minute": self.limit},
                            "request_id": getattr(request.state, "request_id", None),
                        }
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            window.append(now)

        return await call_next(request)


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject oversized payloads before they are buffered."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            if int(content_length) > settings.max_upload_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "payload_too_large",
                            "message": (
                                f"Request body exceeds the "
                                f"{settings.max_upload_bytes // (1024 * 1024)} MB limit."
                            ),
                            "details": None,
                            "request_id": getattr(request.state, "request_id", None),
                        }
                    },
                )
        return await call_next(request)
