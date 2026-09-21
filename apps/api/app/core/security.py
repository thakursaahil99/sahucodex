"""Password hashing, JWT access tokens, and opaque one-time / refresh tokens."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings

JWT_ISSUER = "sahucodex"
JWT_AUDIENCE = "sahucodex-api"


# --- Passwords (Argon2id) ------------------------------------------------------------------


@lru_cache
def _hasher(time_cost: int, memory_kib: int, parallelism: int) -> PasswordHasher:
    return PasswordHasher(time_cost=time_cost, memory_cost=memory_kib, parallelism=parallelism)


def _hasher_for(settings: Settings) -> PasswordHasher:
    return _hasher(settings.argon2_time_cost, settings.argon2_memory_kib, settings.argon2_parallelism)


def hash_password(password: str, settings: Settings) -> str:
    return _hasher_for(settings).hash(password)


def verify_password(password_hash: str, password: str, settings: Settings) -> bool:
    try:
        return _hasher_for(settings).verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str, settings: Settings) -> bool:
    return _hasher_for(settings).check_needs_rehash(password_hash)


def burn_password_check(password: str, settings: Settings) -> None:
    """Spend the same time as a real verification so unknown accounts are not detectable by timing."""
    dummy = _dummy_hash(settings.argon2_time_cost, settings.argon2_memory_kib, settings.argon2_parallelism)
    verify_password(dummy, password, settings)


@lru_cache
def _dummy_hash(time_cost: int, memory_kib: int, parallelism: int) -> str:
    return _hasher(time_cost, memory_kib, parallelism).hash(secrets.token_urlsafe(16))


# --- Opaque tokens (refresh, email verification, password reset) ---------------------------


def generate_opaque_token() -> str:
    """256 bits of entropy. Only the SHA-256 digest is ever stored."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- JWT access tokens ---------------------------------------------------------------------


class TokenError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID
    token_id: str
    expires_at: datetime


def create_access_token(user_id: uuid.UUID, session_id: uuid.UUID, settings: Settings) -> tuple[str, int]:
    """Returns (token, seconds_until_expiry).

    The token deliberately carries no role: authorization is always evaluated against the
    database, so demotions and bans take effect immediately.
    """
    now = datetime.now(UTC)
    expires_in = settings.jwt_access_expire
    payload = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "sub": str(user_id),
        "sid": str(session_id),
        "jti": uuid.uuid4().hex,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str, settings: Settings) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "sid", "jti", "iss", "aud"]},
        )
        if payload.get("type") != "access":
            raise TokenError("TOKEN_INVALID", "Invalid access token")
        return AccessClaims(
            user_id=uuid.UUID(payload["sub"]),
            session_id=uuid.UUID(payload["sid"]),
            token_id=payload["jti"],
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("TOKEN_EXPIRED", "Access token has expired") from exc
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise TokenError("TOKEN_INVALID", "Invalid access token") from exc
