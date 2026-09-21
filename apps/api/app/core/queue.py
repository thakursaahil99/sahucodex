"""Job queue producer. The API only *enqueues* jobs; it never executes user code and never imports the judge.

Production uses Celery over Redis (queues: `judge`, and reserved `ai`, `notifications`, `analytics`). Tests inject a
fake `JobQueue`. Payloads carry identifiers only (a submission id or a run id): the worker loads the source from
the database or Redis itself, so no code, credentials or personal data travel through the broker.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from fastapi import Request

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)

TASK_JUDGE_SUBMISSION = "sahujudge.judge_submission"
TASK_RUN_CODE = "sahujudge.run_code"

QUEUE_JUDGE = "judge"
QUEUE_AI = "ai"
QUEUE_NOTIFICATIONS = "notifications"
QUEUE_ANALYTICS = "analytics"


class QueueUnavailableError(RuntimeError):
    """The broker could not be reached; the job was NOT enqueued."""


class JobQueue(Protocol):
    async def enqueue(self, task: str, *args: str, queue: str) -> None: ...


class CeleryJobQueue:
    def __init__(self, broker_url: str) -> None:
        from celery import Celery  # imported lazily: tests and tooling that never enqueue do not need it

        self._app = Celery("sahucodex-producer", broker=broker_url)
        self._app.conf.update(
            task_serializer="json",
            broker_connection_retry_on_startup=True,
            broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 3},
        )

    def _send(self, task: str, args: tuple[str, ...], queue: str) -> None:
        self._app.send_task(
            task,
            args=list(args),
            queue=queue,
            retry=True,
            retry_policy={"max_retries": 2, "interval_start": 0.1, "interval_step": 0.2, "interval_max": 0.5},
        )

    async def enqueue(self, task: str, *args: str, queue: str) -> None:
        try:
            await asyncio.to_thread(self._send, task, args, queue)
        except Exception as exc:  # kombu raises a variety of transport errors
            log.error("queue_enqueue_failed", task=task, queue=queue, error=type(exc).__name__)
            raise QueueUnavailableError(str(exc)) from exc


class UnavailableJobQueue:
    """Stands in when no worker is deployed: callers get the same clean error as a broker outage."""

    async def enqueue(self, task: str, *args: str, queue: str) -> None:
        raise QueueUnavailableError("no job worker is deployed (JUDGE_ENABLED=false)")


def build_job_queue(settings: Settings) -> JobQueue:
    if not settings.judge_enabled:
        return UnavailableJobQueue()
    return CeleryJobQueue(settings.redis_url)


def get_job_queue(request: Request) -> JobQueue:
    return request.app.state.queue
