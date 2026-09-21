"""Pure-ASGI middleware (no BaseHTTPMiddleware, so streaming and websockets stay intact)."""

from __future__ import annotations

import re
import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import error_body
from app.core.logging import get_logger
from app.core.metrics import Metrics
from app.core.net import client_ip_from_scope

log = get_logger("sahucodex.http")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_QUIET_PATHS = {"/health", "/ready", "/metrics"}


def route_template(scope: Scope) -> str:
    """Low-cardinality route label for metrics, e.g. `/api/users/{username}`.

    FastAPI reports a route relative to the router it was included from, so the `/api` prefix
    of our versionless API router has to be restored to keep labels unambiguous."""
    path = getattr(scope.get("route"), "path", None)
    if path is None:
        return "unmatched"
    if scope["path"].startswith("/api/") and not path.startswith("/api"):
        return "/api" + path
    return path


class RequestContextMiddleware:
    """Assigns a request id, emits one structured access-log line, and records HTTP metrics."""

    def __init__(self, app: ASGIApp, settings: Settings, metrics: Metrics) -> None:
        self.app = app
        self.settings = settings
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        ip = client_ip_from_scope(scope, self.settings.trusted_proxy_count)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        status_code = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            route = route_template(scope)
            method = scope["method"]
            self.metrics.http_requests.labels(method, route, str(status_code)).inc()
            self.metrics.http_duration.labels(method, route).observe(duration)
            path = scope["path"]
            level = "debug" if path in _QUIET_PATHS and status_code < 500 else "info"
            if status_code >= 500:
                level = "error"
            getattr(log, level)(
                "http_request",
                method=method,
                path=path,
                status=status_code,
                duration_ms=round(duration * 1000, 1),
                ip=ip,
            )
            structlog.contextvars.clear_contextvars()


_API_CSP = "default-src 'none'; frame-ancestors 'none'"
# Swagger UI is served by FastAPI and loads its assets from jsDelivr.
_DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
    "frame-ancestors 'none'"
)
_NO_STORE_PREFIXES = ("/api/auth", "/api/users/me", "/api/admin")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.hsts = settings.is_production

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        is_docs = path.startswith("/api/docs")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                headers["Content-Security-Policy"] = _DOCS_CSP if is_docs else _API_CSP
                if self.hsts:
                    headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
                if path.startswith(_NO_STORE_PREFIXES) and "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_wrapper)


class BodySizeLimitMiddleware:
    """Rejects oversized bodies, including chunked uploads that declare no Content-Length."""

    def __init__(self, app: ASGIApp, max_bytes: int, overrides: dict[str, int] | None = None) -> None:
        self.app = app
        self.default_max = max_bytes
        self.overrides = overrides or {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self._limit_for(scope)
        declared = dict(scope["headers"]).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            await self._reject(scope, receive, send, limit)
            return

        received = 0
        rejected = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    if not response_started and not rejected:
                        # Answer right now: the app would otherwise turn our cut-off into a 400.
                        rejected = True
                        await self._reject(scope, receive, send, limit)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if rejected:
                return  # the 413 is already on the wire; drop whatever the app tries to say
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not rejected:
                raise  # the disconnect we forced is expected to upset the app; anything else is not

    def _limit_for(self, scope: Scope) -> int:
        """FastAPI reads a body *before* it evaluates auth dependencies, so a raised limit is only granted to
        requests that at least present a bearer token. (Anonymous callers keep the small default.)"""
        headers = dict(scope["headers"])
        if headers.get(b"authorization", b"")[:7].lower() == b"bearer ":
            for prefix, limit in self.overrides.items():
                if scope["path"].startswith(prefix):
                    return limit
        return self.default_max

    async def _reject(self, scope: Scope, receive: Receive, send: Send, limit: int) -> None:
        response = JSONResponse(error_body("PAYLOAD_TOO_LARGE", f"Request body exceeds {limit} bytes"), status_code=413)
        await response(scope, receive, send)
