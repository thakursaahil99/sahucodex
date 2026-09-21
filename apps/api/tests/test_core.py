"""Unit tests for config parsing, security primitives, rate limiter, IP resolution and log redaction."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import fakeredis
import jwt
import pytest
from pydantic import ValidationError

from app.core.config import RateLimit, Settings, parse_duration, parse_rate_limit
from app.core.logging import redact_sensitive
from app.core.net import client_ip_from_scope
from app.core.rate_limit import RateLimiter
from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from tests.conftest import make_settings

# --- Config ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "seconds"), [("30s", 30), ("15m", 900), ("12h", 43200), ("7d", 604800), ("120", 120), (45, 45)]
)
def test_parse_duration(raw, seconds):
    assert parse_duration(raw) == seconds


@pytest.mark.parametrize("bad", ["", "abc", "10x", "-5m", "1.5h"])
def test_parse_duration_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_duration(bad)


def test_parse_rate_limit():
    assert parse_rate_limit("5/minute") == RateLimit(5, 60)
    assert parse_rate_limit("300 / hour") == RateLimit(300, 3600)
    with pytest.raises(ValueError):
        parse_rate_limit("5 per minute")


def test_duration_and_rate_settings_come_from_strings():
    s = make_settings(jwt_access_expire="30m", jwt_refresh_expire="14d", rate_limit_login="3/second")
    assert (s.jwt_access_expire, s.jwt_refresh_expire, s.rate_limit_login) == (1800, 14 * 86400, RateLimit(3, 1))


def test_cors_origins_are_split_and_normalised():
    s = make_settings(cors_origins="http://a.test/, http://b.test")
    assert s.cors_origins == ["http://a.test", "http://b.test"]


def test_database_url_is_upgraded_to_the_async_driver():
    assert make_settings(database_url="postgresql://u:p@db/x").database_url == "postgresql+asyncpg://u:p@db/x"
    assert make_settings(database_url="postgres://u:p@db/x").database_url == "postgresql+asyncpg://u:p@db/x"


def test_short_jwt_secret_is_rejected():
    with pytest.raises(ValidationError, match="at least 32"):
        make_settings(jwt_secret="too-short")


def test_production_refuses_unsafe_configuration():
    good = {"app_env": "production", "jwt_secret": "x" * 40, "email_backend": "smtp"}
    assert make_settings(**good).use_secure_cookies is True
    with pytest.raises(ValidationError, match="placeholder"):
        make_settings(**{**good, "jwt_secret": "dev-only-change-me-" + "x" * 30})
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        make_settings(**good, cookie_secure=False)
    with pytest.raises(ValidationError, match="EMAIL_BACKEND"):
        make_settings(**{**good, "email_backend": "console"})


_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_settings_load_from_real_environment_variables(monkeypatch):
    """Values arrive as strings from the environment, which takes a different path than kwargs."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/x")
    monkeypatch.setenv("REDIS_URL", "redis://r:6379/0")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("RATE_LIMIT_LOGIN", "7/minute")
    monkeypatch.setenv("JWT_ACCESS_EXPIRE", "20m")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test,http://b.test")
    s = Settings(_env_file=None)
    assert s.rate_limit_login == RateLimit(7, 60)
    assert s.jwt_access_expire == 1200
    assert s.cors_origins == ["http://a.test", "http://b.test"]


def test_the_shipped_env_example_is_a_valid_configuration(monkeypatch):
    """Guards .env.example against typos and formats the app cannot parse."""
    for key in list(os.environ):
        if key.upper() in Settings.model_fields or key.startswith(("SEED_", "POSTGRES_", "REDIS_")):
            monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=_REPO_ROOT / ".env.example")
    assert s.metrics_token is None  # `METRICS_TOKEN=` is "unset", not an empty secret
    assert s.app_env == "development"
    assert s.rate_limit_login == RateLimit(5, 60)
    assert s.jwt_access_expire == 900 and s.jwt_refresh_expire == 7 * 86400
    assert s.database_url.startswith("postgresql+asyncpg://")
    assert s.email_backend == "console"


# --- Passwords & tokens ----------------------------------------------------------------------


def test_password_hashing_uses_argon2id_with_unique_salts():
    s = make_settings()
    first, second = hash_password("correct-horse", s), hash_password("correct-horse", s)
    assert first.startswith("$argon2id$") and first != second
    assert verify_password(first, "correct-horse", s)
    assert not verify_password(first, "wrong-horse", s)
    assert not verify_password("not-a-hash", "correct-horse", s)


def test_hashes_created_with_weaker_parameters_are_flagged_for_rehash():
    weak = make_settings()
    strong = make_settings(argon2_time_cost=2, argon2_memory_kib=16)
    old = hash_password("correct-horse", weak)
    assert password_needs_rehash(old, strong)
    assert not password_needs_rehash(old, weak)


def test_hash_token_is_deterministic_and_not_reversible_looking():
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("abd")
    assert len(hash_token("abc")) == 64


def test_access_token_round_trip_and_claims():
    s = make_settings()
    user, session = uuid.uuid4(), uuid.uuid4()
    token, expires_in = create_access_token(user, session, s)
    claims = decode_access_token(token, s)
    assert (claims.user_id, claims.session_id, expires_in) == (user, session, 900)
    payload = jwt.decode(token, options={"verify_signature": False})
    assert "role" not in payload and "roles" not in payload and "email" not in payload


def _forge(**overrides: object) -> str:
    """A correctly signed token whose claims differ from what the API issues."""
    now = int(time.time())
    claims: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
        "jti": "x",
        "iss": "sahucodex",
        "aud": "sahucodex-api",
        "type": "access",
        "iat": now,
        "exp": now + 60,
    }
    claims.update(overrides)
    return jwt.encode(claims, make_settings().jwt_secret.get_secret_value(), algorithm="HS256")


def test_access_token_with_wrong_audience_is_rejected():
    with pytest.raises(TokenError) as exc:
        decode_access_token(_forge(aud="someone-else"), make_settings())
    assert exc.value.code == "TOKEN_INVALID"


def test_token_of_another_type_cannot_be_used_as_an_access_token():
    with pytest.raises(TokenError):
        decode_access_token(_forge(type="refresh"), make_settings())


# --- Rate limiter ----------------------------------------------------------------------------


def _limiter(**overrides) -> RateLimiter:
    redis = fakeredis.FakeAsyncRedis(server=fakeredis.FakeServer(), decode_responses=True)
    return RateLimiter(redis, make_settings(**overrides))


async def test_rate_limiter_allows_up_to_the_limit_then_blocks_with_retry_after():
    limiter = _limiter()
    limit = RateLimit(3, 60)
    results = [await limiter.hit("t", "ip", limit) for _ in range(5)]
    assert [r.allowed for r in results] == [True, True, True, False, False]
    assert 1 <= results[-1].retry_after <= 60


async def test_rate_limiter_buckets_are_independent():
    limiter = _limiter()
    limit = RateLimit(1, 60)
    assert (await limiter.hit("t", "a", limit)).allowed
    assert not (await limiter.hit("t", "a", limit)).allowed
    assert (await limiter.hit("t", "b", limit)).allowed
    assert (await limiter.hit("other", "a", limit)).allowed


async def test_rate_limiter_window_slides(monkeypatch):
    limiter = _limiter()
    limit = RateLimit(2, 10)
    now = time.time()
    monkeypatch.setattr("app.core.rate_limit.time.time", lambda: now)
    assert (await limiter.hit("t", "a", limit)).allowed
    assert (await limiter.hit("t", "a", limit)).allowed
    assert not (await limiter.hit("t", "a", limit)).allowed
    monkeypatch.setattr("app.core.rate_limit.time.time", lambda: now + 11)
    assert (await limiter.hit("t", "a", limit)).allowed


async def test_rejected_requests_do_not_extend_the_block(monkeypatch):
    limiter = _limiter()
    limit = RateLimit(1, 10)
    now = time.time()
    monkeypatch.setattr("app.core.rate_limit.time.time", lambda: now)
    assert (await limiter.hit("t", "a", limit)).allowed
    for offset in (1, 2, 3, 4):  # hammering while blocked...
        monkeypatch.setattr("app.core.rate_limit.time.time", lambda offset=offset: now + offset)
        assert not (await limiter.hit("t", "a", limit)).allowed
    monkeypatch.setattr("app.core.rate_limit.time.time", lambda: now + 10.5)  # ...must not delay recovery
    assert (await limiter.hit("t", "a", limit)).allowed


async def test_rate_limiter_fails_open_when_redis_is_unavailable():
    from redis.exceptions import ConnectionError as RedisConnectionError

    class Broken:
        def pipeline(self, *a, **k):
            raise RedisConnectionError("down")

    limiter = RateLimiter(Broken(), make_settings())  # type: ignore[arg-type]
    assert (await limiter.hit("t", "a", RateLimit(1, 60))).allowed


# --- Client IP -------------------------------------------------------------------------------


def _scope(peer: str, xff: str | None) -> dict:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return {"client": (peer, 1234), "headers": headers}


def test_forwarded_header_is_ignored_without_trusted_proxies():
    assert client_ip_from_scope(_scope("10.0.0.5", "1.2.3.4"), 0) == "10.0.0.5"


def test_only_the_trusted_hop_is_believed():
    # Attacker sends "X-Forwarded-For: 6.6.6.6"; our single trusted proxy appends the real peer.
    assert client_ip_from_scope(_scope("172.18.0.3", "6.6.6.6, 203.0.113.9"), 1) == "203.0.113.9"
    assert client_ip_from_scope(_scope("172.18.0.3", "6.6.6.6, 203.0.113.9, 10.0.0.1"), 2) == "203.0.113.9"


def test_missing_or_short_forwarded_chain_falls_back_to_the_peer():
    assert client_ip_from_scope(_scope("172.18.0.3", None), 1) == "172.18.0.3"
    assert client_ip_from_scope(_scope("172.18.0.3", "203.0.113.9"), 2) == "172.18.0.3"


# --- Log redaction ---------------------------------------------------------------------------


def test_sensitive_log_fields_are_redacted():
    event = redact_sensitive(
        None,
        "info",
        {
            "event": "x",
            "password": "hunter2",
            "refresh_token": "abc",
            "Authorization": "Bearer abc",
            "code": "print(1)",
            "nested": {"api_key": "k", "safe": "ok"},
            "user_id": "42",
        },
    )
    assert event["password"] == event["refresh_token"] == event["Authorization"] == event["code"] == "[REDACTED]"
    assert event["nested"] == {"api_key": "[REDACTED]", "safe": "ok"}
    assert event["user_id"] == "42"
