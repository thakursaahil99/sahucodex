"""Real-time submission events over Redis pub/sub and an authenticated WebSocket.

Publishers (the API and the judge worker) call `publish_event`; the WebSocket endpoint subscribes to the *user's own*
channel, so a connection can only ever receive events about that user's submissions.

Authentication: browsers cannot set headers on a WebSocket, and putting the access token in the URL would leak it into
proxy logs. Instead an authenticated `POST /api/ws/ticket` mints a random, single-use, 30-second ticket bound to the
user; the socket redeems it once. Tickets are stored only as SHA-256 digests.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger

log = get_logger(__name__)

EVENT_QUEUED = "submission.queued"
EVENT_RUNNING = "submission.running"
EVENT_COMPLETED = "submission.completed"
EVENT_FAILED = "submission.failed"
EVENT_RUN_RUNNING = "run.running"
EVENT_RUN_COMPLETED = "run.completed"
EVENT_RUN_FAILED = "run.failed"
EVENT_ACHIEVEMENT_EARNED = "achievement.earned"


def user_channel(user_id: uuid.UUID | str) -> str:
    return f"events:user:{user_id}"


def _ticket_key(ticket: str) -> str:
    return "ws:ticket:" + hashlib.sha256(ticket.encode()).hexdigest()


async def publish_event(redis: Redis, user_id: uuid.UUID | str, event_type: str, data: dict[str, Any]) -> None:
    """Best effort: a lost notification must never fail a submission, because clients also poll the REST endpoint."""
    message = json.dumps(
        {"type": event_type, "data": data, "ts": datetime.now(UTC).isoformat()}, separators=(",", ":"), default=str
    )
    try:
        await redis.publish(user_channel(user_id), message)
    except RedisError as exc:
        log.warning("event_publish_failed", event=event_type, error=type(exc).__name__)


async def issue_ticket(redis: Redis, user_id: uuid.UUID, ttl_seconds: int) -> str:
    ticket = secrets.token_urlsafe(32)
    await redis.set(_ticket_key(ticket), str(user_id), ex=ttl_seconds)
    return ticket


async def redeem_ticket(redis: Redis, ticket: str) -> uuid.UUID | None:
    """Single use: GETDEL makes redemption atomic, so a replayed or raced ticket only ever works once."""
    if not 20 <= len(ticket) <= 100:
        return None
    try:
        raw = await redis.getdel(_ticket_key(ticket))
        return uuid.UUID(raw) if raw else None
    except (RedisError, ValueError):
        return None
