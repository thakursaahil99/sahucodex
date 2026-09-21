"""Connects the engine to PostgreSQL and Redis: claim a job, judge it, persist the outcome, tell the user.

Everything that touches hidden tests happens here and in `engine`; nothing in this module ever puts test data into an
event, a log line or a stored row (only verdicts, runtimes, memory and counts are stored).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cache import Cache
from app.core.config import Settings
from app.core.db import utcnow
from app.core.logging import get_logger
from app.modules.problems.models import CaseKind, Problem, ProblemTestCase, ProgressStatus, UserProblemProgress
from app.modules.problems.service import detail_cache_key
from app.modules.profiles import service as profiles
from app.modules.profiles.models import Achievement
from app.modules.submissions import events, runs
from app.modules.submissions.models import (
    Submission,
    SubmissionResult,
    SubmissionStatus,
    SubmissionTestResult,
)
from sahujudge import JUDGE_VERSION
from sahujudge.checkers import get_checker
from sahujudge.engine import (
    CaseOutcome,
    JudgeConfig,
    JudgeReport,
    JudgeTest,
    Verdict,
    effective_time_limit_ms,
    judge_tests,
    run_custom,
)
from sahujudge.languages import get_language
from sahujudge.sandbox import Sandbox

log = get_logger(__name__)

RUN_DISPLAY_CHARS = 8192  # what a Run shows per stream; the stored/returned copy is truncated, not the execution
MESSAGE_MAX = 300


@dataclass
class JudgeDeps:
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: Redis
    sandbox: Sandbox
    settings: Settings

    @property
    def config(self) -> JudgeConfig:
        s = self.settings
        return JudgeConfig(
            max_output_bytes=s.judge_max_output_bytes,
            max_stderr_bytes=s.judge_max_stderr_bytes,
            max_tests=s.judge_max_tests,
        )


@dataclass(frozen=True)
class ProblemSpec:
    id: uuid.UUID
    slug: str
    time_limit_ms: int
    memory_limit_mb: int
    checker: str


async def _load_problem(db: AsyncSession, problem_id: uuid.UUID | None = None, slug: str | None = None) -> ProblemSpec:
    stmt = select(Problem.id, Problem.slug, Problem.time_limit_ms, Problem.memory_limit_mb, Problem.checker)
    stmt = stmt.where(Problem.id == problem_id) if problem_id else stmt.where(Problem.slug == slug)
    row = (await db.execute(stmt)).one()
    return ProblemSpec(*row)


async def _load_tests(db: AsyncSession, problem_id: uuid.UUID, *, public_only: bool) -> list[JudgeTest]:
    """The ONLY place hidden tests are read. `public_only` keeps them out of memory entirely for Run."""
    stmt = select(ProblemTestCase).where(ProblemTestCase.problem_id == problem_id)
    if public_only:
        stmt = stmt.where(ProblemTestCase.kind == CaseKind.PUBLIC.value)
    rows = (await db.execute(stmt.order_by(ProblemTestCase.position, ProblemTestCase.id))).scalars().all()
    return [
        JudgeTest(
            input=row.input_data, expected=row.expected_output, public=row.kind == CaseKind.PUBLIC.value, id=str(row.id)
        )
        for row in rows
    ]


# --- submissions ------------------------------------------------------------------------------------------------------


async def _claim(db: AsyncSession, submission_id: uuid.UUID) -> bool:
    """QUEUED -> RUNNING, atomically. A duplicate delivery (or a re-run of a finished job) claims nothing and stops."""
    result = await db.execute(
        update(Submission)
        .where(Submission.id == submission_id, Submission.status == SubmissionStatus.QUEUED.value)
        .values(status=SubmissionStatus.RUNNING.value, started_at=utcnow())
    )
    await db.commit()
    return result.rowcount == 1  # type: ignore[attr-defined]


async def record_progress(db: AsyncSession, user_id: uuid.UUID, problem_id: uuid.UUID, *, accepted: bool) -> None:
    """Upserts `user_problem_progress` without a read-modify-write, so concurrent judgments cannot lose an attempt."""
    now = utcnow()
    values: dict[str, Any] = {"attempts": UserProblemProgress.attempts + 1, "last_attempt_at": now}
    if accepted:  # SOLVED is never downgraded: a later wrong answer leaves it alone
        values["status"] = ProgressStatus.SOLVED.value
        values["first_solved_at"] = func.coalesce(UserProblemProgress.first_solved_at, now)
    where = (UserProblemProgress.user_id == user_id, UserProblemProgress.problem_id == problem_id)

    if (await db.execute(update(UserProblemProgress).where(*where).values(**values))).rowcount:  # type: ignore[attr-defined]
        return
    try:
        async with db.begin_nested():
            db.add(
                UserProblemProgress(
                    user_id=user_id,
                    problem_id=problem_id,
                    status=ProgressStatus.SOLVED.value if accepted else ProgressStatus.ATTEMPTED.value,
                    attempts=1,
                    first_solved_at=now if accepted else None,
                    last_attempt_at=now,
                )
            )
            await db.flush()
    except IntegrityError:  # another worker created the row between our UPDATE and INSERT
        await db.execute(update(UserProblemProgress).where(*where).values(**values))


def _clip(text: str | None, limit: int) -> str | None:
    return None if text is None else text[:limit]


async def _persist(
    deps: JudgeDeps, submission: Submission, problem: ProblemSpec, effective_limit_ms: int, report: JudgeReport
) -> list[Achievement]:
    """Persists the verdict and everything derived from it. Returns any achievements newly earned, for the caller to
    announce — after its own "submission.completed" event, so a client sees the verdict before the celebration."""
    async with deps.sessionmaker() as db:
        row = await db.get(Submission, submission.id)
        assert row is not None
        row.status = SubmissionStatus.COMPLETED.value
        row.verdict = report.verdict.value
        row.runtime_ms = report.runtime_ms
        row.memory_kb = report.memory_kb
        row.passed_count = report.passed
        row.total_count = report.total  # the count at judging time, which is the truth if an admin edited the tests
        row.finished_at = utcnow()
        db.add(
            SubmissionResult(
                submission_id=row.id,
                compile_output=_clip(report.compile_output, deps.settings.judge_max_compile_output_bytes),
                message=_clip(report.message, MESSAGE_MAX),
                checker=problem.checker,
                judge_version=JUDGE_VERSION,
                time_limit_ms=effective_limit_ms,
                memory_limit_mb=problem.memory_limit_mb,
            )
        )
        db.add_all(
            SubmissionTestResult(
                submission_id=row.id,
                test_case_id=uuid.UUID(o.test_id) if o.test_id else None,
                position=o.position,
                is_public=o.public,
                verdict=o.verdict.value,
                runtime_ms=o.time_ms,
                memory_kb=o.memory_kb,
            )
            for o in report.outcomes
        )
        await db.execute(
            update(Problem)
            .where(Problem.id == problem.id)
            .values(
                total_submissions=Problem.total_submissions + 1,
                accepted_submissions=Problem.accepted_submissions + (1 if report.verdict is Verdict.ACCEPTED else 0),
            )
        )
        await record_progress(db, row.user_id, problem.id, accepted=report.verdict is Verdict.ACCEPTED)
        if report.verdict is Verdict.ACCEPTED:
            await profiles.record_streak(db, row.user_id)
        # Runs after every judged submission, not just accepted ones: a count-based achievement (100 submissions)
        # can become true on a failing attempt too. Cheap next to everything else a judged submission already costs.
        newly_earned = await profiles.evaluate_achievements(db, row.user_id)
        earned_details = (
            (await db.scalars(select(Achievement).where(Achievement.key.in_(newly_earned)))).all()
            if newly_earned
            else []
        )
        await db.commit()
    await Cache(deps.redis).delete(detail_cache_key(problem.slug))  # the cached statement shows acceptance stats
    return list(earned_details)


async def _fail(deps: JudgeDeps, submission_id: uuid.UUID, user_id: uuid.UUID, reason: str) -> None:
    """The judge itself failed. The submission is closed as SYSTEM_ERROR and does NOT count as an attempt."""
    async with deps.sessionmaker() as db:
        await db.execute(
            update(Submission)
            .where(Submission.id == submission_id)
            .values(status=SubmissionStatus.FAILED.value, verdict=Verdict.SYSTEM_ERROR.value, finished_at=utcnow())
        )
        await db.commit()
    await events.publish_event(
        deps.redis,
        user_id,
        events.EVENT_FAILED,
        {
            "submission_id": str(submission_id),
            "status": SubmissionStatus.FAILED.value,
            "verdict": Verdict.SYSTEM_ERROR.value,
            "message": reason,
        },
    )


async def judge_submission(deps: JudgeDeps, submission_id: uuid.UUID) -> str:
    """Judges one submission. Returns what happened (for logs and tests): a verdict, `skipped` or `failed`."""
    async with deps.sessionmaker() as db:
        if not await _claim(db, submission_id):
            log.info("submission_skipped", submission_id=str(submission_id), reason="not queued")
            return "skipped"
        submission = await db.get(Submission, submission_id)
        assert submission is not None

    await events.publish_event(
        deps.redis,
        submission.user_id,
        events.EVENT_RUNNING,
        {"submission_id": str(submission_id), "status": SubmissionStatus.RUNNING.value},
    )
    try:
        async with deps.sessionmaker() as db:
            problem = await _load_problem(db, problem_id=submission.problem_id)
            tests = await _load_tests(db, problem.id, public_only=False)  # hidden tests: server side only
        language = get_language(submission.language_key)
        report = await judge_tests(
            deps.sandbox,
            language=language,
            source=submission.source_code,
            tests=tests,
            time_limit_ms=problem.time_limit_ms,
            memory_limit_mb=problem.memory_limit_mb,
            checker=get_checker(problem.checker),
            config=deps.config,
        )
        earned = await _persist(
            deps, submission, problem, effective_time_limit_ms(problem.time_limit_ms, language), report
        )
    except Exception as exc:  # any failure of the judge is SYSTEM_ERROR, never a verdict about the user's code
        log.error("judge_failed", submission_id=str(submission_id), error=type(exc).__name__, exc_info=True)
        await _fail(deps, submission_id, submission.user_id, "The judge could not complete this submission.")
        return "failed"

    await events.publish_event(
        deps.redis,
        submission.user_id,
        events.EVENT_COMPLETED,
        {
            "submission_id": str(submission_id),
            "status": SubmissionStatus.COMPLETED.value,
            "verdict": report.verdict.value,
            "runtime_ms": report.runtime_ms,
            "memory_kb": report.memory_kb,
            "passed": report.passed,
            "total": report.total,
        },
    )
    for achievement in earned:
        await events.publish_event(
            deps.redis,
            submission.user_id,
            events.EVENT_ACHIEVEMENT_EARNED,
            {"key": achievement.key, "name": achievement.name, "icon": achievement.icon},
        )
    log.info("submission_judged", submission_id=str(submission_id), verdict=report.verdict.value, passed=report.passed)
    return report.verdict.value


# --- runs -------------------------------------------------------------------------------------------------------------


def _shown(text: str | None) -> str | None:
    if text is None:
        return None
    return text if len(text) <= RUN_DISPLAY_CHARS else text[:RUN_DISPLAY_CHARS] + "\n… (truncated)"


def _case_out(outcome: CaseOutcome) -> dict[str, Any]:
    return {
        "position": outcome.position,
        "verdict": outcome.verdict.value,
        "input": _shown(outcome.input) or "",
        "expected_output": _shown(outcome.expected) or "",
        "stdout": _shown(outcome.stdout) or "",
        "stderr": _shown(outcome.stderr) or "",
        "message": outcome.message,
        "runtime_ms": outcome.time_ms,
        "memory_kb": outcome.memory_kb,
    }


async def run_code(deps: JudgeDeps, run_id: str) -> str:
    record = await runs.load_run_record(deps.redis, run_id)
    if record is None or record.get("status") != "QUEUED":
        return "skipped"
    ttl = deps.settings.run_result_ttl
    request, user_id = record["request"], uuid.UUID(record["user_id"])
    record["status"] = "RUNNING"
    await runs.store_run_record(deps.redis, run_id, record, ttl_seconds=ttl)
    await events.publish_event(deps.redis, user_id, events.EVENT_RUN_RUNNING, {"run_id": run_id})

    try:
        async with deps.sessionmaker() as db:
            problem = await _load_problem(db, slug=request["problem_slug"])
            tests = await _load_tests(db, problem.id, public_only=True) if record["mode"] == "samples" else []
        language = get_language(request["language"])
        if record["mode"] == "samples":
            report = await judge_tests(
                deps.sandbox,
                language=language,
                source=request["source_code"],
                tests=tests,
                time_limit_ms=problem.time_limit_ms,
                memory_limit_mb=problem.memory_limit_mb,
                checker=get_checker(problem.checker),
                config=deps.config,
                stop_on_failure=False,
                capture_public=True,
            )
            result: dict[str, Any] = {
                "outcome": report.verdict.value,
                "compile_output": _shown(report.compile_output),
                "message": report.message,
                "runtime_ms": report.runtime_ms,
                "memory_kb": report.memory_kb,
                "cases": [_case_out(o) for o in report.outcomes],
            }
        else:
            custom = await run_custom(
                deps.sandbox,
                language=language,
                source=request["source_code"],
                stdin=request.get("input") or "",
                time_limit_ms=problem.time_limit_ms,
                memory_limit_mb=problem.memory_limit_mb,
                config=deps.config,
            )
            result = {
                "outcome": str(custom.status),
                "compile_output": _shown(custom.compile_output),
                "stdout": _shown(custom.stdout),
                "stderr": _shown(custom.stderr),
                "message": custom.message,
                "runtime_ms": custom.time_ms,
                "memory_kb": custom.memory_kb,
            }
    except Exception as exc:
        log.error("run_failed", run_id=run_id, error=type(exc).__name__, exc_info=True)
        failed = {
            "user_id": str(user_id),
            "mode": record["mode"],
            "status": "FAILED",
            "error": "The judge could not run this code.",
        }
        await runs.store_run_record(deps.redis, run_id, failed, ttl_seconds=ttl)
        await events.publish_event(deps.redis, user_id, events.EVENT_RUN_FAILED, {"run_id": run_id})
        return "failed"

    done = {"user_id": str(user_id), "mode": record["mode"], "status": "COMPLETED", "result": result}  # source dropped
    await runs.store_run_record(deps.redis, run_id, done, ttl_seconds=ttl)
    await events.publish_event(
        deps.redis, user_id, events.EVENT_RUN_COMPLETED, {"run_id": run_id, "outcome": result["outcome"]}
    )
    return str(result["outcome"])
