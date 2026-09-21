"""Operational endpoints for orchestrators and Prometheus. Mounted at the root (not under /api)."""

from __future__ import annotations

import asyncio
import hmac

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.core.errors import unauthorized
from app.core.logging import get_logger

router = APIRouter(tags=["operations"])
log = get_logger(__name__)

_CHECK_TIMEOUT_SECONDS = 2.0


@router.get("/health", summary="Liveness: the process is up")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness: PostgreSQL and Redis are reachable")
async def ready(request: Request) -> JSONResponse:
    checks: dict[str, str] = {}

    async def check_database() -> None:
        async with request.app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def check_redis() -> None:
        await request.app.state.redis.ping()

    for name, probe in (("database", check_database), ("redis", check_redis)):
        try:
            await asyncio.wait_for(probe(), timeout=_CHECK_TIMEOUT_SECONDS)
            checks[name] = "ok"
        except Exception as exc:
            # Details go to the logs only; the response must not reveal infrastructure internals.
            log.error("readiness_check_failed", dependency=name, error=type(exc).__name__)
            checks[name] = "unavailable"

    ok = all(value == "ok" for value in checks.values())
    return JSONResponse({"status": "ready" if ok else "not_ready", "checks": checks}, status_code=200 if ok else 503)


@router.get("/metrics", summary="Prometheus metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    token = request.app.state.settings.metrics_token
    if token is not None:
        header = request.headers.get("authorization", "")
        supplied = header[7:] if header.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(supplied.encode(), token.get_secret_value().encode()):
            raise unauthorized("METRICS_UNAUTHORIZED", "Metrics token required")
    return Response(generate_latest(request.app.state.metrics.registry), media_type=CONTENT_TYPE_LATEST)
