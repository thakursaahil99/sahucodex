"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis_asyncio
from fastapi import APIRouter, Depends, FastAPI
from redis.asyncio import Redis
from starlette.middleware.cors import CORSMiddleware

from app.core.cache import Cache
from app.core.config import Settings, get_settings
from app.core.db import create_engine_from_settings, create_sessionmaker
from app.core.email import EmailSender, build_email_sender
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.metrics import Metrics
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.queue import JobQueue, build_job_queue
from app.core.rate_limit import RateLimiter, general_rate_limit
from app.modules.admin.router import router as admin_router
from app.modules.ai.provider import AiProvider, build_ai_provider
from app.modules.ai.router import router as ai_router
from app.modules.auth.router import router as auth_router
from app.modules.health.router import router as health_router
from app.modules.problems.router import router as problems_router
from app.modules.profiles.router import router as profiles_router
from app.modules.submissions.router import router as submissions_router
from app.modules.submissions.router import ws_router
from app.modules.users.router import router as users_router

log = get_logger(__name__)

API_DESCRIPTION = """
**SahuCodeX API** — *Code. Compete. Learn.*

Errors always use the envelope `{"success": false, "error": {"code": "...", "message": "..."}}`.
Authenticate with `Authorization: Bearer <access_token>`; the refresh token lives in an httpOnly cookie.
"""


def create_app(
    settings: Settings | None = None,
    *,
    redis_client: Redis | None = None,
    email_sender: EmailSender | None = None,
    job_queue: JobQueue | None = None,
    ai_provider: AiProvider | None = None,
) -> FastAPI:
    """Builds the app. Dependencies can be injected (tests do), otherwise they come from settings."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_logs=settings.is_production)

    engine = create_engine_from_settings(settings)
    redis_conn = redis_client or redis_asyncio.from_url(settings.redis_url, decode_responses=True)
    metrics = Metrics()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("api_starting", env=settings.app_env)
        yield
        await redis_conn.aclose()
        await engine.dispose()
        log.info("api_stopped")

    app = FastAPI(
        title="SahuCodeX API",
        version="0.1.0",
        description=API_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/api/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.docs_enabled else None,
    )

    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = create_sessionmaker(engine)
    app.state.redis = redis_conn
    app.state.rate_limiter = RateLimiter(redis_conn, settings)
    app.state.cache = Cache(redis_conn)
    app.state.email_sender = email_sender or build_email_sender(settings)
    app.state.queue = job_queue or build_job_queue(settings)
    app.state.ai_provider = ai_provider or build_ai_provider(settings)
    app.state.metrics = metrics

    register_exception_handlers(app)

    # Middleware runs outermost -> innermost in reverse order of registration.
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=settings.max_request_bytes,
        overrides={"/api/admin/": settings.admin_max_request_bytes},
    )
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware, settings=settings, metrics=metrics)

    api = APIRouter(prefix="/api", dependencies=[Depends(general_rate_limit)])
    api.include_router(auth_router)
    api.include_router(users_router)
    api.include_router(problems_router)
    api.include_router(profiles_router)
    api.include_router(submissions_router)
    api.include_router(ai_router)
    api.include_router(admin_router)

    app.include_router(health_router)
    app.include_router(api)
    app.include_router(ws_router)
    return app
