"""Small JSON cache on Redis. Every operation fails soft: a Redis outage means cache misses, not errors."""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger

log = get_logger(__name__)

PREFIX = "cache:"


class Cache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_json(self, key: str) -> Any | None:
        try:
            raw = await self._redis.get(PREFIX + key)
        except RedisError as exc:
            log.warning("cache_unavailable", op="get", error=type(exc).__name__)
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None

    async def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        try:
            await self._redis.set(PREFIX + key, json.dumps(value, separators=(",", ":")), ex=ttl_seconds)
        except RedisError as exc:
            log.warning("cache_unavailable", op="set", error=type(exc).__name__)

    async def delete(self, *keys: str) -> None:
        if not keys:
            return
        try:
            await self._redis.delete(*(PREFIX + key for key in keys))
        except RedisError as exc:
            # A stale entry will expire on its own TTL; log loudly because it may serve outdated data.
            log.error("cache_invalidation_failed", error=type(exc).__name__)
