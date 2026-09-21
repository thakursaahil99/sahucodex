"""Builds the worker's dependencies from settings, once per task (each Celery task runs in its own event loop)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis_asyncio

from app.core.config import Settings
from app.core.db import create_engine_from_settings, create_sessionmaker
from sahujudge.docker_sandbox import DockerSandbox, DockerSandboxConfig
from sahujudge.pipeline import JudgeDeps
from sahujudge.sandbox import Sandbox


def build_sandbox(settings: Settings) -> DockerSandbox:
    return DockerSandbox(
        DockerSandboxConfig(
            image=settings.sandbox_image,
            docker_bin=settings.sandbox_docker_bin,
            docker_host=settings.sandbox_docker_host,
            runtime=settings.sandbox_runtime,
            pids_limit=settings.sandbox_pids_limit,
            cpus=settings.sandbox_cpus,
            tmpfs_mb=settings.sandbox_tmpfs_mb,
            max_source_bytes=settings.submission_max_source_bytes,
            compile_output_bytes=settings.judge_max_compile_output_bytes,
        )
    )


@asynccontextmanager
async def open_deps(settings: Settings, sandbox: Sandbox | None = None) -> AsyncIterator[JudgeDeps]:
    engine = create_engine_from_settings(settings)
    redis = redis_asyncio.from_url(settings.redis_url, decode_responses=True)
    try:
        yield JudgeDeps(
            sessionmaker=create_sessionmaker(engine),
            redis=redis,
            sandbox=sandbox or build_sandbox(settings),
            settings=settings,
        )
    finally:
        await redis.aclose()
        await engine.dispose()
