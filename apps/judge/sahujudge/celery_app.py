"""The Celery application:  celery -A sahujudge.celery_app worker -Q judge --concurrency 2 -B

`-B` embeds the beat scheduler for the periodic reaper; run exactly ONE worker with `-B` (or a separate `celery beat`).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from celery import Celery
from celery.signals import worker_ready

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.log_level, json_logs=settings.is_production)
log = get_logger(__name__)

celery_app = Celery("sahujudge", broker=settings.redis_url, include=["sahujudge.tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,  # outcomes live in PostgreSQL / Redis records, never in a Celery result backend
    task_default_queue="judge",
    task_routes={"sahujudge.*": {"queue": "judge"}},
    # Acknowledge after the task, so a worker that dies mid-job has its message redelivered. The pipeline's atomic
    # QUEUED -> RUNNING claim makes that redelivery harmless (the job is skipped, and the reaper closes it).
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # one job at a time per process: judging is long and CPU-heavy
    worker_max_tasks_per_child=200,
    task_soft_time_limit=840,
    task_time_limit=900,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    beat_schedule={"reap-stale": {"task": "sahujudge.reap_stale", "schedule": 300.0}},
    timezone="UTC",
)


@worker_ready.connect
def prepare_sandbox(**_: Any) -> None:
    """Make sure the runner image exists in the sandbox daemon, and sweep containers a previous worker left behind."""
    from sahujudge.runtime import build_sandbox  # imported here: runtime imports the pipeline, which imports this app

    if not settings.sandbox_auto_build:
        return
    sandbox = build_sandbox(settings)

    async def prepare() -> None:
        built = await sandbox.ensure_image(Path(settings.sandbox_build_context))
        await sandbox.reap_stale(0)  # nothing of ours can be running yet
        log.info("sandbox_ready", image=settings.sandbox_image, built=built)

    asyncio.run(prepare())
