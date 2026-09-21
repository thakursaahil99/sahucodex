"""Authentication and authorization dependencies. Every protected route goes through these."""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import BackgroundTasks, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import DbSession, EmailSenderDep, RedisDep, SettingsDep
from app.core.errors import AppError, forbidden, unauthorized
from app.core.logging import get_logger
from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.core.security import AccessClaims, TokenError, decode_access_token
from app.modules.auth.service import AuthService, is_session_revoked
from app.modules.users.models import RoleName, User

log = get_logger(__name__)
_bearer = HTTPBearer(auto_error=False, description="Access token returned by /api/auth/login")

# Higher rank includes everything below it: an ADMIN may do anything a MODERATOR may.
_ROLE_RANK = {RoleName.USER: 1, RoleName.MODERATOR: 2, RoleName.ADMIN: 3}


async def _verify(credentials: HTTPAuthorizationCredentials, settings: Settings, redis: Redis) -> AccessClaims:
    if credentials.scheme.lower() != "bearer":
        raise unauthorized()
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except TokenError as exc:
        raise unauthorized(exc.code, exc.message) from exc
    try:
        revoked = await is_session_revoked(redis, claims.session_id)
    except RedisError as exc:
        # Fail closed: without the denylist we cannot prove the session was not revoked.
        log.error("session_denylist_unavailable", error=type(exc).__name__)
        raise AppError(503, "SERVICE_UNAVAILABLE", "Authentication is temporarily unavailable") from exc
    if revoked:
        raise unauthorized("TOKEN_REVOKED", "This session has been signed out")
    return claims


async def _load_user(db: AsyncSession, claims: AccessClaims) -> User:
    user = await db.get(User, claims.user_id)
    if user is None or user.deleted_at is not None or not user.is_active:
        raise unauthorized("ACCOUNT_UNAVAILABLE", "This account is not available")
    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    return user


async def get_auth_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: SettingsDep,
    redis: RedisDep,
) -> AccessClaims:
    if credentials is None:
        raise unauthorized()
    return await _verify(credentials, settings, redis)


async def get_current_user(claims: Annotated[AccessClaims, Depends(get_auth_claims)], db: DbSession) -> User:
    return await _load_user(db, claims)


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: SettingsDep,
    redis: RedisDep,
    db: DbSession,
) -> User | None:
    """For public endpoints that personalise their answer. No credentials = anonymous; credentials that are
    present but bad are still rejected (so the client refreshes an expired token instead of silently degrading)."""
    if credentials is None:
        return None
    return await _load_user(db, await _verify(credentials, settings, redis))


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def current_session_id(claims: Annotated[AccessClaims, Depends(get_auth_claims)]) -> uuid.UUID:
    return claims.session_id


CurrentSessionId = Annotated[uuid.UUID, Depends(current_session_id)]


def require_role(minimum: RoleName):
    """Dependency factory: `Depends(require_role(RoleName.ADMIN))`. Evaluated on the server against
    the database on every call — never against anything the client sent."""

    async def checker(user: CurrentUser) -> User:
        rank = max((_ROLE_RANK.get(RoleName(role), 0) for role in user.roles), default=0)
        if rank < _ROLE_RANK[minimum]:
            log.warning("authz_denied", user_id=str(user.id), required=str(minimum))
            raise forbidden()
        return user

    return checker


def get_auth_service(
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    email: EmailSenderDep,
    background: BackgroundTasks,
) -> AuthService:
    return AuthService(db, redis, settings, limiter, email, background)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def verify_origin(request: Request, settings: SettingsDep) -> None:
    """CSRF defence for endpoints authenticated by the refresh cookie.

    Browsers always attach `Origin` to cross-site POSTs, so a request whose Origin is not one of
    ours is a forged cross-site request. Requests with no Origin come from non-browser clients,
    which are not subject to CSRF. Combined with SameSite=Lax cookies this closes the gap."""
    origin = request.headers.get("origin")
    if origin is not None and origin.rstrip("/") not in settings.allowed_origins:
        log.warning("csrf_origin_rejected", origin=origin[:100])
        raise forbidden("CSRF_ORIGIN_MISMATCH", "Cross-site request rejected")
