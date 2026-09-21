"""The serverless queue runs the judge inside `enqueue` and reports failures as a queue outage."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.core.config import Settings
from app.core.queue import (
    QUEUE_JUDGE,
    TASK_JUDGE_SUBMISSION,
    TASK_RUN_CODE,
    InlineJobQueue,
    QueueUnavailableError,
    UnavailableJobQueue,
    build_job_queue,
)
from sahujudge import pipeline, runtime


def _settings(**extra: Any) -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        jwt_secret="x" * 40,
        _env_file=None,
        **extra,
    )


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    calls: list[tuple[str, Any]] = []

    @asynccontextmanager
    async def fake_open_deps(settings: Settings):  # type: ignore[no-untyped-def]
        yield "deps"

    async def fake_judge(deps: Any, submission_id: uuid.UUID) -> str:
        calls.append(("judge", submission_id))
        return "ok"

    async def fake_run(deps: Any, run_id: str) -> str:
        calls.append(("run", run_id))
        return "ok"

    monkeypatch.setattr(runtime, "open_deps", fake_open_deps)
    monkeypatch.setattr(pipeline, "judge_submission", fake_judge)
    monkeypatch.setattr(pipeline, "run_code", fake_run)
    return calls


def test_backend_selection() -> None:
    assert isinstance(build_job_queue(_settings(judge_backend="vercel")), InlineJobQueue)
    assert isinstance(build_job_queue(_settings(judge_backend="vercel", judge_enabled=False)), UnavailableJobQueue)


async def test_enqueue_judges_before_returning(recorded: list[tuple[str, Any]]) -> None:
    queue = InlineJobQueue(_settings())
    submission_id = uuid.uuid4()

    await queue.enqueue(TASK_JUDGE_SUBMISSION, str(submission_id), queue=QUEUE_JUDGE)
    await queue.enqueue(TASK_RUN_CODE, "run-1", queue=QUEUE_JUDGE)

    assert recorded == [("judge", submission_id), ("run", "run-1")]


async def test_unknown_tasks_are_refused() -> None:
    with pytest.raises(QueueUnavailableError):
        await InlineJobQueue(_settings()).enqueue("something.else", "x", queue="ai")


async def test_pipeline_crash_is_reported_as_queue_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def fake_open_deps(settings: Settings):  # type: ignore[no-untyped-def]
        yield "deps"

    async def boom(deps: Any, submission_id: uuid.UUID) -> str:
        raise RuntimeError("sandbox exploded")

    monkeypatch.setattr(runtime, "open_deps", fake_open_deps)
    monkeypatch.setattr(pipeline, "judge_submission", boom)

    with pytest.raises(QueueUnavailableError):
        await InlineJobQueue(_settings()).enqueue(TASK_JUDGE_SUBMISSION, str(uuid.uuid4()), queue=QUEUE_JUDGE)
