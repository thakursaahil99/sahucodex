"""Celery tasks. Each is a thin synchronous wrapper: build dependencies, run the async pipeline, tear down."""

from __future__ import annotations

import asyncio
import uuid

from app.core.config import get_settings
from sahujudge import pipeline, reaper
from sahujudge.celery_app import celery_app
from sahujudge.runtime import build_sandbox, open_deps


@celery_app.task(name="sahujudge.judge_submission")
def judge_submission(submission_id: str) -> str:
    async def go() -> str:
        async with open_deps(get_settings()) as deps:
            return await pipeline.judge_submission(deps, uuid.UUID(submission_id))

    return asyncio.run(go())


@celery_app.task(name="sahujudge.run_code")
def run_code(run_id: str) -> str:
    async def go() -> str:
        async with open_deps(get_settings()) as deps:
            return await pipeline.run_code(deps, run_id)

    return asyncio.run(go())


@celery_app.task(name="sahujudge.reap_stale")
def reap_stale() -> dict[str, int]:
    async def go() -> dict[str, int]:
        settings = get_settings()
        sandbox = build_sandbox(settings)
        async with open_deps(settings, sandbox) as deps:
            return {
                "submissions": await reaper.fail_stale_submissions(deps),
                "containers": await reaper.reap_containers(sandbox, settings.judge_stale_after),
            }

    return asyncio.run(go())
