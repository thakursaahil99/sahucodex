"""Hosted-Postgres URLs (Neon etc.) are libpq-style; asyncpg needs them rewritten."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.queue import QueueUnavailableError, UnavailableJobQueue, build_job_queue


def _settings(database_url: str, **extra: object) -> Settings:
    return Settings(
        database_url=database_url,
        redis_url="redis://localhost:6379/0",
        jwt_secret="x" * 40,
        _env_file=None,
        **extra,
    )


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgresql://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        ("postgres://u:p@h/db?sslmode=require", "postgresql+asyncpg://u:p@h/db?ssl=require"),
        (
            "postgresql://u:p@h/db?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://u:p@h/db?ssl=require",
        ),
        ("postgresql://u:p@h/db?sslmode=disable", "postgresql+asyncpg://u:p@h/db"),
        ("postgresql+asyncpg://u:p@h/db?ssl=require", "postgresql+asyncpg://u:p@h/db?ssl=require"),
        ("sqlite+aiosqlite://", "sqlite+aiosqlite://"),
    ],
)
def test_database_url_is_made_asyncpg_compatible(given: str, expected: str) -> None:
    assert _settings(given).database_url == expected


async def test_disabled_judge_fails_like_a_broker_outage() -> None:
    queue = build_job_queue(_settings("sqlite+aiosqlite://", judge_enabled=False))
    assert isinstance(queue, UnavailableJobQueue)
    with pytest.raises(QueueUnavailableError):
        await queue.enqueue("sahujudge.judge_submission", "id", queue="judge")
