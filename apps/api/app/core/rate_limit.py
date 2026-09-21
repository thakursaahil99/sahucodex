"""Redis-backed sliding-window rate limiter."""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import RateLimit, Settings
from app.core.errors import rate_limited
from app.core.logging import get_logger
from app.core.net import client_ip

log = get_logger(__name__)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int = 0


class RateLimiter:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._enabled = settings.rate_limit_enabled

    async def hit(self, scope: str, identifier: str, limit: RateLimit) -> RateLimitResult:
        """Record one request. Rejected requests are not counted, so a blocked client
        regains access exactly `window` seconds after its last *allowed* request."""
        if not self._enabled:
            return RateLimitResult(True)
        key = f"rl:{scope}:{identifier}"
        now = time.time()
        member = f"{now}:{uuid.uuid4().hex[:8]}"
        try:
            pipe = self._redis.pipeline(transaction=True)
            pipe.zremrangebyscore(key, 0, now - limit.window_seconds)
            pipe.zadd(key, {member: now})
            pipe.zcard(key)
            pipe.expire(key, limit.window_seconds)
            _, _, count, _ = await pipe.execute()
            if count <= limit.limit:
                return RateLimitResult(True)
            await self._redis.zrem(key, member)
            oldest = await self._redis.zrange(key, 0, 0, withscores=True)
            retry_after = math.ceil(oldest[0][1] + limit.window_seconds - now) if oldest else limit.window_seconds
            return RateLimitResult(False, max(retry_after, 1))
        except RedisError as exc:
            # Availability over strictness: an outage must not lock everyone out of the API.
            log.warning("rate_limit_backend_unavailable", scope=scope, error=type(exc).__name__)
            return RateLimitResult(True)

    async def enforce(self, scope: str, identifier: str, limit: RateLimit) -> None:
        result = await self.hit(scope, identifier, limit)
        if not result.allowed:
            log.warning("rate_limited", scope=scope)
            raise rate_limited(result.retry_after)


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


async def general_rate_limit(request: Request) -> None:
    """Router-level guard applied to every /api route."""
    settings: Settings = request.app.state.settings
    await get_rate_limiter(request).enforce("general", client_ip(request), settings.rate_limit_general)
