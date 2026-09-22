"""Submission and run use cases (API side). Nothing here executes code: it validates, records, enqueues and reads."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.db import utcnow
from app.core.errors import AppError, not_found
from app.core.logging import get_logger
from app.core.pagination import PageParams
from app.core.queue import QUEUE_JUDGE, TASK_JUDGE_SUBMISSION, TASK_RUN_CODE, JobQueue, QueueUnavailableError
from app.modules.problems.models import CaseKind, Problem, ProblemTestCase, ProgrammingLanguage
from app.modules.submissions import events, runs
from app.modules.submissions.models import Submission, SubmissionStatus, SubmissionTestResult, Verdict
from app.modules.submissions.schemas import (
    PublicTestResult,
    RunCreate,
    RunOut,
    RunResultOut,
    SubmissionCreate,
    SubmissionDetail,
    SubmissionSummary,
)
from app.modules.users.models import User

log = get_logger(__name__)


@dataclass(frozen=True)
class ProblemRef:
    """What the API needs to know about a problem: never its tests' contents (they are loaded by the worker only)."""

    id: uuid.UUID
    slug: str
    title: str
    time_limit_ms: int
    memory_limit_mb: int


async def resolve_language(db: AsyncSession, language_key: str) -> str:
    """Shared by every submit path (plain and contest): a language must exist and be enabled."""
    language = await db.get(ProgrammingLanguage, language_key)
    if language is None:
        raise AppError(422, "UNKNOWN_LANGUAGE", f"Unknown language: {language_key}")
    if not language.is_enabled:
        raise AppError(422, "LANGUAGE_DISABLED", f"{language.display_name} is not available right now")
    return language.key


async def _resolve(db: AsyncSession, slug: str, language_key: str) -> tuple[ProblemRef, str]:
    row = (
        await db.execute(
            select(Problem.id, Problem.slug, Problem.title, Problem.time_limit_ms, Problem.memory_limit_mb).where(
                Problem.slug == slug, Problem.published.is_(True), Problem.archived_at.is_(None)
            )
        )
    ).first()
    if row is None:
        raise not_found("PROBLEM_NOT_FOUND", "Problem not found")
    language_key = await resolve_language(db, language_key)
    return ProblemRef(*row), language_key


def validate_source(settings: Settings, source: str, *, limit: int | None = None) -> None:
    size = len(source.encode("utf-8"))
    if size > (limit or settings.submission_max_source_bytes):
        raise AppError(
            422,
            "SOURCE_TOO_LARGE",
            f"Source code is limited to {(limit or settings.submission_max_source_bytes) // 1024} KiB",
        )
    if "\x00" in source:
        raise AppError(422, "INVALID_SOURCE", "Source code must not contain NUL bytes")
    if not source.strip():
        raise AppError(422, "INVALID_SOURCE", "Source code is empty")


async def _count_tests(db: AsyncSession, problem_id: uuid.UUID, kind: CaseKind | None = None) -> int:
    stmt = select(func.count()).select_from(ProblemTestCase).where(ProblemTestCase.problem_id == problem_id)
    if kind is not None:
        stmt = stmt.where(ProblemTestCase.kind == kind.value)
    return (await db.execute(stmt)).scalar_one()


# --- submissions ------------------------------------------------------------------------------------------------------


async def _too_many_pending(db: AsyncSession, settings: Settings, user: User) -> bool:
    horizon = utcnow() - timedelta(seconds=settings.judge_stale_after)
    in_flight = (
        await db.execute(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.user_id == user.id,
                Submission.status.in_([SubmissionStatus.QUEUED.value, SubmissionStatus.RUNNING.value]),
                Submission.created_at > horizon,
            )
        )
    ).scalar_one()
    return in_flight >= settings.max_inflight_submissions


async def create_and_enqueue(
    db: AsyncSession,
    redis: Redis,
    queue: JobQueue,
    settings: Settings,
    user: User,
    problem: ProblemRef,
    language_key: str,
    source_code: str,
    *,
    contest_id: uuid.UUID | None = None,
) -> Submission:
    """The part every submit path shares: create the durable row, enqueue the job, publish the event.

    Callers resolve `problem`/`language_key` themselves first (the plain path requires `published`; the contest path
    instead requires contest membership and timing — see contests/service.py), and validate `source_code` themselves
    (`validate_source`, possibly with a contest-specific size limit) before calling this.
    """
    if await _too_many_pending(db, settings, user):
        raise AppError(
            429,
            "TOO_MANY_PENDING_SUBMISSIONS",
            "You already have submissions being judged. Wait for one to finish.",
            headers={"Retry-After": "5"},
        )

    total = await _count_tests(db, problem.id)
    if total == 0:
        raise AppError(409, "PROBLEM_NOT_JUDGEABLE", "This problem has no tests yet")

    submission = Submission(
        user_id=user.id,
        problem_id=problem.id,
        language_key=language_key,
        source_code=source_code,
        status=SubmissionStatus.QUEUED.value,
        total_count=total,
        contest_id=contest_id,
    )
    db.add(submission)
    await db.commit()  # the row is durable BEFORE the job is enqueued, so a worker can never see an id that is missing

    try:
        await queue.enqueue(TASK_JUDGE_SUBMISSION, str(submission.id), queue=QUEUE_JUDGE)
    except QueueUnavailableError as exc:
        submission.status = SubmissionStatus.FAILED.value
        submission.verdict = Verdict.SYSTEM_ERROR.value
        submission.finished_at = utcnow()
        await db.commit()
        raise AppError(503, "JUDGE_UNAVAILABLE", "The judge is temporarily unavailable. Please try again.") from exc

    await events.publish_event(
        redis,
        user.id,
        events.EVENT_QUEUED,
        {"submission_id": str(submission.id), "status": SubmissionStatus.QUEUED.value, "problem_slug": problem.slug},
    )
    log.info(
        "submission_queued",
        submission_id=str(submission.id),
        problem=problem.slug,
        language=language_key,
        contest_id=str(contest_id) if contest_id else None,
    )
    return submission


async def create_submission(
    db: AsyncSession, redis: Redis, queue: JobQueue, settings: Settings, user: User, data: SubmissionCreate
) -> Submission:
    problem, language_key = await _resolve(db, data.problem_slug, data.language)
    validate_source(settings, data.source_code)
    return await create_and_enqueue(db, redis, queue, settings, user, problem, language_key, data.source_code)


def _summary(row: tuple[Submission, str, str]) -> SubmissionSummary:
    submission, slug, title = row
    return SubmissionSummary(
        id=submission.id,
        problem_slug=slug,
        problem_title=title,
        language=submission.language_key,
        status=SubmissionStatus(submission.status),
        verdict=Verdict(submission.verdict) if submission.verdict else None,
        runtime_ms=submission.runtime_ms,
        memory_kb=submission.memory_kb,
        passed_count=submission.passed_count,
        total_count=submission.total_count,
        created_at=submission.created_at,
        finished_at=submission.finished_at,
    )


async def list_submissions(
    db: AsyncSession,
    user: User,
    params: PageParams,
    *,
    problem_slug: str | None,
    verdict: Verdict | None,
    language: str | None,
    status: SubmissionStatus | None,
) -> tuple[list[SubmissionSummary], int]:
    base = (
        select(Submission, Problem.slug, Problem.title)
        .join(Problem, Problem.id == Submission.problem_id)
        .where(Submission.user_id == user.id)
    )
    if problem_slug:
        base = base.where(Problem.slug == problem_slug)
    if verdict:
        base = base.where(Submission.verdict == verdict.value)
    if language:
        base = base.where(Submission.language_key == language)
    if status:
        base = base.where(Submission.status == status.value)
    total = (await db.execute(select(func.count()).select_from(base.order_by(None).subquery()))).scalar_one()
    rows = (
        await db.execute(
            base.order_by(Submission.created_at.desc(), Submission.id).offset(params.offset).limit(params.limit)
        )
    ).all()
    return [_summary((s, slug, title)) for s, slug, title in rows], total


async def get_submission_detail(db: AsyncSession, user: User, submission_id: uuid.UUID) -> SubmissionDetail:
    """Owner-only. Anyone else gets the same 404 as for a missing id, so ids cannot be probed."""
    stmt = (
        select(Submission, Problem.slug, Problem.title)
        .join(Problem, Problem.id == Submission.problem_id)
        .where(Submission.id == submission_id, Submission.user_id == user.id)
        .options(selectinload(Submission.result))
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise not_found("SUBMISSION_NOT_FOUND", "Submission not found")
    submission, slug, title = row
    results = (
        (
            await db.execute(
                select(SubmissionTestResult)
                .where(SubmissionTestResult.submission_id == submission.id, SubmissionTestResult.is_public.is_(True))
                .order_by(SubmissionTestResult.position)
            )
        )
        .scalars()
        .all()
    )
    result = submission.result
    summary = _summary((submission, slug, title))
    return SubmissionDetail(
        **summary.model_dump(),
        source_code=submission.source_code,
        compile_output=result.compile_output if result else None,
        message=result.message if result else None,
        time_limit_ms=result.time_limit_ms if result else None,
        memory_limit_mb=result.memory_limit_mb if result else None,
        test_results=[
            PublicTestResult(
                position=r.position, verdict=Verdict(r.verdict), runtime_ms=r.runtime_ms, memory_kb=r.memory_kb
            )
            for r in results
        ],
    )


# --- runs -------------------------------------------------------------------------------------------------------------


async def run_for(
    db: AsyncSession,
    redis: Redis,
    queue: JobQueue,
    settings: Settings,
    user: User,
    problem: ProblemRef,
    language_key: str,
    source_code: str,
    mode: str,
    stdin: str | None,
) -> str:
    """The part every run path shares, once the problem/language are already resolved — see `create_and_enqueue`,
    the same split for submissions."""
    validate_source(settings, source_code)
    if mode == "custom":
        stdin = stdin or ""
        if len(stdin.encode("utf-8")) > settings.run_max_input_bytes:
            raise AppError(422, "INPUT_TOO_LARGE", f"Input is limited to {settings.run_max_input_bytes // 1024} KiB")
        if "\x00" in stdin:
            raise AppError(422, "INVALID_INPUT", "Input must not contain NUL bytes")
    elif await _count_tests(db, problem.id, CaseKind.PUBLIC) == 0:
        raise AppError(409, "NO_SAMPLES", "This problem has no public examples to run against")

    run_id = runs.new_run_id()
    await runs.create_run_record(
        redis,
        run_id,
        user_id=user.id,
        mode=mode,
        request={
            "problem_slug": problem.slug,
            "language": language_key,
            "source_code": source_code,
            "input": stdin if mode == "custom" else None,
        },
        ttl_seconds=settings.run_result_ttl,
    )
    try:
        await queue.enqueue(TASK_RUN_CODE, run_id, queue=QUEUE_JUDGE)
    except QueueUnavailableError as exc:
        await redis.delete(runs.run_key(run_id))
        raise AppError(503, "JUDGE_UNAVAILABLE", "The judge is temporarily unavailable. Please try again.") from exc
    return run_id


async def create_run(
    db: AsyncSession, redis: Redis, queue: JobQueue, settings: Settings, user: User, data: RunCreate
) -> str:
    problem, language_key = await _resolve(db, data.problem_slug, data.language)
    return await run_for(
        db, redis, queue, settings, user, problem, language_key, data.source_code, data.mode, data.input
    )


async def get_run(redis: Redis, user: User, run_id: str) -> RunOut:
    record = await runs.load_run_record(redis, run_id)
    if record is None or record.get("user_id") != str(user.id):
        raise not_found("RUN_NOT_FOUND", "Run not found or expired")
    result = record.get("result")
    return RunOut(
        id=run_id,
        status=record["status"],
        mode=record["mode"],
        result=RunResultOut.model_validate(result) if result else None,
        error=record.get("error"),
    )
