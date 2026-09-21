"""Authentication use-cases: registration, login, refresh-token rotation, sessions, email flows."""

from __future__ import annotations

import contextlib
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import BackgroundTasks
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import utcnow
from app.core.email import EmailSender, send_email_safely
from app.core.errors import AppError, conflict, not_found, unauthorized
from app.core.logging import get_logger
from app.core.rate_limit import RateLimiter
from app.core.security import (
    burn_password_check,
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.modules.audit.service import record_audit
from app.modules.auth.models import OneTimeToken, RefreshToken, RevokeReason, TokenPurpose
from app.modules.users import service as users
from app.modules.users.models import User

log = get_logger(__name__)

REVOKED_SESSION_KEY = "auth:revoked_session:{}"


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_max_age: int
    refresh_token_id: uuid.UUID
    session_id: uuid.UUID
    user: User


async def is_session_revoked(redis: Redis, session_id: uuid.UUID) -> bool:
    return bool(await redis.exists(REVOKED_SESSION_KEY.format(session_id)))


class AuthService:
    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        settings: Settings,
        limiter: RateLimiter,
        email: EmailSender,
        background: BackgroundTasks,
    ) -> None:
        self.db = db
        self.redis = redis
        self.settings = settings
        self.limiter = limiter
        self.email = email
        self.background = background

    # --- Registration -----------------------------------------------------------------------

    async def register(self, *, email: str, username: str, password: str, ip: str, user_agent: str | None) -> User:
        if username.lower() in users.RESERVED_USERNAMES:
            raise conflict("USERNAME_TAKEN", "That username is not available")
        if await users.get_by_email(self.db, email):
            raise conflict("EMAIL_TAKEN", "An account with that email already exists")
        if await users.get_by_username(self.db, username):
            raise conflict("USERNAME_TAKEN", "That username is not available")

        try:
            user = await users.create_user(self.db, self.settings, email=email, username=username, password=password)
            record_audit(self.db, "auth.register", actor_id=user.id, ip=ip, user_agent=user_agent)
            await self.db.commit()
        except IntegrityError as exc:
            # Lost a race against a concurrent registration for the same email/username.
            await self.db.rollback()
            raise conflict("ACCOUNT_EXISTS", "An account with those details already exists") from exc

        log.info("user_registered", user_id=str(user.id))
        await self.send_verification_email(user)
        return user

    # --- Login / sessions ---------------------------------------------------------------------

    async def login(self, *, identifier: str, password: str, ip: str, user_agent: str | None) -> IssuedSession:
        s = self.settings
        account_key = hashlib.sha256(identifier.strip().lower().encode()).hexdigest()[:32]
        await self.limiter.enforce("login:ip", ip, s.rate_limit_login)
        await self.limiter.enforce("login:account", account_key, s.rate_limit_login_account)

        user = await users.get_by_identifier(self.db, identifier)
        if user is None or user.deleted_at is not None:
            burn_password_check(password, s)  # keep timing similar to a real verification
            log.warning("auth_login_failed", reason="unknown_account", ip=ip)
            raise unauthorized("INVALID_CREDENTIALS", "Invalid email/username or password")

        if not verify_password(user.password_hash, password, s):
            log.warning("auth_login_failed", reason="bad_password", user_id=str(user.id), ip=ip)
            record_audit(self.db, "auth.login_failed", actor_id=user.id, ip=ip, user_agent=user_agent)
            await self.db.commit()
            raise unauthorized("INVALID_CREDENTIALS", "Invalid email/username or password")

        if not user.is_active:
            log.warning("auth_login_blocked", reason="inactive", user_id=str(user.id))
            raise AppError(403, "ACCOUNT_DISABLED", "This account has been disabled")

        if password_needs_rehash(user.password_hash, s):
            user.password_hash = hash_password(password, s)
        user.last_login_at = utcnow()
        session = await self._issue_session(user, ip=ip, user_agent=user_agent)
        record_audit(self.db, "auth.login", actor_id=user.id, ip=ip, user_agent=user_agent)
        await self.db.commit()
        await self._reset_account_limit(account_key)
        log.info("auth_login_succeeded", user_id=str(user.id))
        return session

    async def refresh(self, raw_token: str, *, ip: str, user_agent: str | None) -> IssuedSession:
        now = utcnow()
        token = await self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)).with_for_update()
        )
        if token is None:
            raise unauthorized("REFRESH_TOKEN_INVALID", "Invalid refresh token")

        if token.revoked_at is not None:
            await self._handle_revoked_token(token, now, ip, user_agent)  # always raises

        if token.expires_at <= now:
            raise unauthorized("REFRESH_TOKEN_EXPIRED", "Session expired, please sign in again")

        user = await self.db.get(User, token.user_id)
        if user is None or user.deleted_at is not None or not user.is_active:
            await self._revoke_family(token.family_id, RevokeReason.SESSION_REVOKED)
            await self.db.commit()
            await self._deny_access_tokens([token.family_id])
            raise unauthorized("ACCOUNT_UNAVAILABLE", "This account is not available")

        session = await self._issue_session(user, ip=ip, user_agent=user_agent, family_id=token.family_id)
        # Insert the successor first: the UPDATE below references it through a foreign key, and
        # SQLAlchemy would otherwise order that UPDATE ahead of the INSERT.
        await self.db.flush()
        token.revoked_at = now
        token.revoked_reason = RevokeReason.ROTATED
        token.replaced_by_id = session.refresh_token_id
        await self.db.commit()
        return session

    async def _handle_revoked_token(self, token: RefreshToken, now: datetime, ip: str, user_agent: str | None) -> None:
        if token.revoked_reason != RevokeReason.ROTATED:
            raise unauthorized("REFRESH_TOKEN_INVALID", "Invalid refresh token")

        assert token.revoked_at is not None
        if now - token.revoked_at <= timedelta(seconds=self.settings.refresh_reuse_grace_seconds):
            # Two tabs (or a retry) presented the same token within moments of each other.
            # Not proof of theft: ask the client to retry with the cookie it just received.
            raise unauthorized("REFRESH_TOKEN_RACE", "Session was just refreshed elsewhere; retry")

        # A rotated token replayed later means someone kept a copy. Kill the whole session.
        await self._revoke_family(token.family_id, RevokeReason.REUSE_DETECTED)
        record_audit(
            self.db, "auth.refresh_reuse_detected", actor_id=token.user_id,
            target_type="session", target_id=str(token.family_id), ip=ip, user_agent=user_agent,
        )  # fmt: skip
        await self.db.commit()
        await self._deny_access_tokens([token.family_id])
        log.warning("auth_refresh_reuse_detected", user_id=str(token.user_id), session_id=str(token.family_id), ip=ip)
        raise unauthorized("REFRESH_TOKEN_REUSED", "Session is no longer valid, please sign in again")

    async def logout(self, raw_token: str | None, *, ip: str, user_agent: str | None) -> None:
        """Idempotent: ends the session the refresh cookie belongs to, if any."""
        if not raw_token:
            return
        token = await self.db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
        if token is None:
            return
        await self._revoke_family(token.family_id, RevokeReason.LOGOUT)
        record_audit(self.db, "auth.logout", actor_id=token.user_id, ip=ip, user_agent=user_agent)
        await self.db.commit()
        await self._deny_access_tokens([token.family_id])

    async def list_sessions(self, user: User, current_session: uuid.UUID) -> list[tuple[RefreshToken, bool]]:
        rows = await self.db.scalars(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > utcnow(),
            )
            .order_by(RefreshToken.created_at.desc())
        )
        return [(row, row.family_id == current_session) for row in rows]

    async def revoke_session(self, user: User, session_id: uuid.UUID, *, ip: str, user_agent: str | None) -> None:
        owned = await self.db.scalar(
            select(RefreshToken.id)
            .where(RefreshToken.family_id == session_id, RefreshToken.user_id == user.id)
            .limit(1)
        )
        if owned is None:
            raise not_found("SESSION_NOT_FOUND", "Session not found")
        await self._revoke_family(session_id, RevokeReason.SESSION_REVOKED)
        record_audit(
            self.db, "auth.session_revoked", actor_id=user.id, target_type="session",
            target_id=str(session_id), ip=ip, user_agent=user_agent,
        )  # fmt: skip
        await self.db.commit()
        await self._deny_access_tokens([session_id])

    # --- Email verification ---------------------------------------------------------------------

    async def send_verification_email(self, user: User) -> None:
        if user.is_email_verified:
            return
        raw = await self._create_one_time_token(user, TokenPurpose.EMAIL_VERIFY, self.settings.email_verify_expire)
        link = f"{self.settings.frontend_url.rstrip('/')}/verify-email?token={raw}"
        self.background.add_task(
            send_email_safely,
            self.email,
            user.email,
            "Verify your SahuCodeX email",
            f"Hi {user.username},\n\nConfirm your email address to finish setting up SahuCodeX:\n{link}\n\n"
            "This link expires in 24 hours. If you did not create an account, ignore this message.\n",
        )

    async def verify_email(self, raw_token: str) -> None:
        record = await self._consume_one_time_token(raw_token, TokenPurpose.EMAIL_VERIFY)
        user = await self.db.get(User, record.user_id)
        if user is not None and user.email_verified_at is None:
            user.email_verified_at = utcnow()
            record_audit(self.db, "auth.email_verified", actor_id=user.id)
        await self.db.commit()

    # --- Password reset ---------------------------------------------------------------------------

    async def forgot_password(self, email: str, *, ip: str) -> None:
        """Always completes silently so callers cannot learn which emails are registered."""
        s = self.settings
        await self.limiter.enforce("pwreset:ip", ip, s.rate_limit_password_reset)
        digest = hashlib.sha256(users.normalise_email(email).encode()).hexdigest()[:32]
        await self.limiter.enforce("pwreset:email", digest, s.rate_limit_password_reset)

        user = await users.get_by_email(self.db, email)
        if user is None or user.deleted_at is not None or not user.is_active:
            return
        raw = await self._create_one_time_token(user, TokenPurpose.PASSWORD_RESET, s.password_reset_expire)
        link = f"{s.frontend_url.rstrip('/')}/reset-password?token={raw}"
        self.background.add_task(
            send_email_safely,
            self.email,
            user.email,
            "Reset your SahuCodeX password",
            f"Hi {user.username},\n\nUse this link to choose a new password:\n{link}\n\n"
            "It expires in 1 hour and can be used once. If you did not ask for this, ignore this message.\n",
        )

    async def reset_password(self, raw_token: str, new_password: str, *, ip: str, user_agent: str | None) -> None:
        record = await self._consume_one_time_token(raw_token, TokenPurpose.PASSWORD_RESET)
        user = await self.db.get(User, record.user_id)
        if user is None or user.deleted_at is not None:
            raise AppError(400, "TOKEN_INVALID", "This link is invalid or has expired")
        user.password_hash = hash_password(new_password, self.settings)
        families = await self._revoke_all_sessions(user.id, RevokeReason.PASSWORD_RESET)
        record_audit(self.db, "auth.password_reset", actor_id=user.id, ip=ip, user_agent=user_agent)
        await self.db.commit()
        await self._deny_access_tokens(families)
        log.info("auth_password_reset", user_id=str(user.id))

    # --- Internals ------------------------------------------------------------------------------------

    async def _issue_session(
        self, user: User, *, ip: str, user_agent: str | None, family_id: uuid.UUID | None = None
    ) -> IssuedSession:
        s = self.settings
        family = family_id or uuid.uuid4()
        raw = generate_opaque_token()
        token_id = uuid.uuid4()
        self.db.add(
            RefreshToken(
                id=token_id,
                user_id=user.id,
                family_id=family,
                token_hash=hash_token(raw),
                expires_at=utcnow() + timedelta(seconds=s.jwt_refresh_expire),
                ip_address=ip[:45],
                user_agent=user_agent,
            )
        )
        access, expires_in = create_access_token(user.id, family, s)
        return IssuedSession(access, expires_in, raw, s.jwt_refresh_expire, token_id, family, user)

    async def _create_one_time_token(self, user: User, purpose: TokenPurpose, ttl_seconds: int) -> str:
        # Only the newest link stays valid.
        await self.db.execute(
            update(OneTimeToken)
            .where(OneTimeToken.user_id == user.id, OneTimeToken.purpose == purpose, OneTimeToken.used_at.is_(None))
            .values(used_at=utcnow())
        )
        raw = generate_opaque_token()
        self.db.add(
            OneTimeToken(
                user_id=user.id,
                purpose=purpose,
                token_hash=hash_token(raw),
                expires_at=utcnow() + timedelta(seconds=ttl_seconds),
            )
        )
        await self.db.commit()
        return raw

    async def _consume_one_time_token(self, raw: str, purpose: TokenPurpose) -> OneTimeToken:
        record = await self.db.scalar(
            select(OneTimeToken).where(OneTimeToken.token_hash == hash_token(raw)).with_for_update()
        )
        now = utcnow()
        if record is None or record.purpose != purpose or record.used_at is not None or record.expires_at <= now:
            raise AppError(400, "TOKEN_INVALID", "This link is invalid or has expired")
        record.used_at = now
        return record

    async def _revoke_family(self, family_id: uuid.UUID, reason: RevokeReason) -> None:
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow(), revoked_reason=reason)
        )

    async def _revoke_all_sessions(self, user_id: uuid.UUID, reason: RevokeReason) -> list[uuid.UUID]:
        families = list(
            await self.db.scalars(
                select(RefreshToken.family_id)
                .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
                .distinct()
            )
        )
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow(), revoked_reason=reason)
        )
        return families

    async def _deny_access_tokens(self, family_ids: list[uuid.UUID]) -> None:
        """Access tokens are stateless, so revoked sessions are denylisted until the longest-lived
        token that could still be in circulation expires."""
        try:
            async with self.redis.pipeline(transaction=False) as pipe:
                for family in family_ids:
                    pipe.set(REVOKED_SESSION_KEY.format(family), "1", ex=self.settings.jwt_access_expire + 5)
                await pipe.execute()
        except RedisError as exc:
            log.error("session_denylist_failed", error=type(exc).__name__)

    async def _reset_account_limit(self, account_key: str) -> None:
        with contextlib.suppress(RedisError):
            await self.redis.delete(f"rl:login:account:{account_key}")
