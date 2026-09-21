"""Ephemeral "Run" jobs (the editor's Run button). They are not submissions: no database row, no progress, no counters.

A run lives in Redis for a few minutes: the request (source, optional stdin) while it is queued, then only the result.
The worker and the API share these helpers, so the record's shape is defined once.
"""

from __future__ import annotations

import json
import re
import secrets
import uuid
from typing import Any

from redis.asyncio import Redis

RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,40}$")


def new_run_id() -> str:
    return secrets.token_urlsafe(16)


def run_key(run_id: str) -> str:
    return f"run:{run_id}"


async def create_run_record(
    redis: Redis, run_id: str, *, user_id: uuid.UUID, mode: str, request: dict[str, Any], ttl_seconds: int
) -> None:
    record = {"user_id": str(user_id), "mode": mode, "status": "QUEUED", "request": request}
    await redis.set(run_key(run_id), json.dumps(record), ex=ttl_seconds)


async def load_run_record(redis: Redis, run_id: str) -> dict[str, Any] | None:
    if not RUN_ID_RE.match(run_id):
        return None
    raw = await redis.get(run_key(run_id))
    return json.loads(raw) if raw else None


async def store_run_record(redis: Redis, run_id: str, record: dict[str, Any], *, ttl_seconds: int) -> None:
    await redis.set(run_key(run_id), json.dumps(record), ex=ttl_seconds)
