"""The worker pipeline end to end: claim -> judge -> persist -> progress -> events.

Programs are run by `TrustedLocalSandbox` (Python written by these tests) or scripted outcomes; neither is the product's
sandbox. What is proven here is the wiring and the rules, not the isolation.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from dbsupport import SECRET_ANSWER, SECRET_INPUT, World, drain, new_world
from sqlalchemy import select, text
from support import ScriptedSandbox, TrustedLocalSandbox, exited, killed

from app.core.cache import Cache
from app.core.db import utcnow
from app.modules.problems.models import Problem, UserProblemProgress
from app.modules.problems.service import detail_cache_key
from app.modules.submissions import runs
from app.modules.submissions.models import Submission, SubmissionResult, SubmissionTestResult
from sahujudge import pipeline, reaper
from sahujudge.sandbox import CompileResult, RunStatus, SandboxError

DOUBLE = "n = int(input())\nprint(n * 2)\n"
WRONG = "n = int(input())\nprint(n * 3)\n"


@pytest_asyncio.fixture
async def local_world():
    world = await new_world(TrustedLocalSandbox(i_understand_this_runs_code_without_isolation=True))
    yield world
    await world.close()


async def scripted_world(respond, **kw) -> tuple[World, ScriptedSandbox]:
    sandbox = ScriptedSandbox(respond, **kw)
    return await new_world(sandbox), sandbox


async def row(world: World, model, *where):
    async with world.sessionmaker() as db:
        return (await db.scalars(select(model).where(*where))).first()


# --- the happy path -----------------------------------------------------------------------------------------------------


async def test_an_accepted_submission_is_judged_stored_counted_and_announced(local_world: World) -> None:
    world = local_world
    user, problem = await world.add_user(), await world.add_problem()
    submission_id = await world.add_submission(user, problem, DOUBLE)
    pubsub = await world.subscribe(user)
    await Cache(world.redis).set_json(detail_cache_key("double"), {"stale": True}, 60)

    outcome = await pipeline.judge_submission(world.deps, submission_id)

    assert outcome == "ACCEPTED"
    saved = await row(world, Submission, Submission.id == submission_id)
    assert (saved.status, saved.verdict, saved.passed_count, saved.total_count) == ("COMPLETED", "ACCEPTED", 3, 3)
    assert saved.runtime_ms is not None
    assert saved.memory_kb is not None
    assert saved.started_at is not None
    assert saved.finished_at is not None
    assert saved.language_key == "python"

    result = await row(world, SubmissionResult, SubmissionResult.submission_id == submission_id)
    assert (result.checker, result.judge_version, result.memory_limit_mb) == ("lines", "1", 128)
    assert result.time_limit_ms == 2000 * 3  # python's multiplier
    async with world.sessionmaker() as db:
        per_test = list(await db.scalars(select(SubmissionTestResult).order_by(SubmissionTestResult.position)))
    assert [(t.position, t.is_public, t.verdict) for t in per_test] == [
        (1, True, "ACCEPTED"),
        (2, False, "ACCEPTED"),
        (3, False, "ACCEPTED"),
    ]

    counted = await row(world, Problem, Problem.id == problem)
    assert (counted.total_submissions, counted.accepted_submissions) == (1, 1)
    progress = await row(world, UserProblemProgress, UserProblemProgress.user_id == user)
    assert (progress.status, progress.attempts) == ("SOLVED", 1)
    assert progress.first_solved_at is not None

    assert await Cache(world.redis).get_json(detail_cache_key("double")) is None  # stale acceptance stats dropped

    seen = await drain(pubsub)
    # The very first ACCEPTED submission also earns "First Blood" (see test_profiles.py for achievements/streak).
    assert [e["type"] for e in seen] == ["submission.running", "submission.completed", "achievement.earned"]
    done = seen[1]["data"]
    assert (done["verdict"], done["passed"], done["total"], done["submission_id"]) == (
        "ACCEPTED",
        3,
        3,
        str(submission_id),
    )
    assert "source" not in json.dumps(seen)


async def test_wrong_answers_are_counted_but_never_downgrade_a_solved_problem(local_world: World) -> None:
    world = local_world
    user, problem = await world.add_user(), await world.add_problem()

    async def attempt(source: str) -> str:
        return await pipeline.judge_submission(world.deps, await world.add_submission(user, problem, source))

    assert await attempt(WRONG) == "WRONG_ANSWER"
    progress = await row(world, UserProblemProgress, UserProblemProgress.user_id == user)
    assert (progress.status, progress.attempts, progress.first_solved_at) == ("ATTEMPTED", 1, None)

    assert await attempt(DOUBLE) == "ACCEPTED"
    solved = await row(world, UserProblemProgress, UserProblemProgress.user_id == user)
    assert (solved.status, solved.attempts) == ("SOLVED", 2)
    first = solved.first_solved_at

    assert await attempt(WRONG) == "WRONG_ANSWER"
    after = await row(world, UserProblemProgress, UserProblemProgress.user_id == user)
    assert (after.status, after.attempts, after.first_solved_at) == ("SOLVED", 3, first)  # still solved

    counted = await row(world, Problem, Problem.id == problem)
    assert (counted.total_submissions, counted.accepted_submissions) == (3, 1)


async def test_the_first_failing_test_decides_and_later_tests_are_not_run(local_world: World) -> None:
    world = local_world
    user = await world.add_user()
    problem = await world.add_problem(
        tests=(("PUBLIC", "1\n", "2\n"), ("HIDDEN", "2\n", "999\n"), ("HIDDEN", "3\n", "6\n"))
    )
    submission_id = await world.add_submission(user, problem, DOUBLE)
    await pipeline.judge_submission(world.deps, submission_id)
    saved = await row(world, Submission, Submission.id == submission_id)
    assert (saved.verdict, saved.passed_count, saved.total_count) == ("WRONG_ANSWER", 1, 3)
    async with world.sessionmaker() as db:
        stored = list(await db.scalars(select(SubmissionTestResult)))
    assert len(stored) == 2  # the third test never ran


async def test_the_problems_checker_is_honoured(local_world: World) -> None:
    world = local_world
    user = await world.add_user()
    spaced = "n = int(input())\nprint(' ', n * 2, ' ')\n"  # prints " 2 " style output with odd spacing
    strict = await world.add_problem("strict", checker="exact", tests=(("PUBLIC", "1\n", "2\n"),))
    loose = await world.add_problem("loose", checker="whitespace", tests=(("PUBLIC", "1\n", "2\n"),))
    assert (
        await pipeline.judge_submission(world.deps, await world.add_submission(user, strict, spaced, total=1))
        == "WRONG_ANSWER"
    )
    assert (
        await pipeline.judge_submission(world.deps, await world.add_submission(user, loose, spaced, total=1))
        == "ACCEPTED"
    )


# --- other verdicts, and the judge's own failures -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("result", "verdict"),
    [
        (killed(RunStatus.TIMEOUT), "TIME_LIMIT_EXCEEDED"),
        (killed(RunStatus.MEMORY), "MEMORY_LIMIT_EXCEEDED"),
        (killed(RunStatus.SIGNALED, signal=11), "RUNTIME_ERROR"),
        (killed(RunStatus.OUTPUT_LIMIT), "RUNTIME_ERROR"),
        (exited("", code=1, stderr="Traceback ..."), "RUNTIME_ERROR"),
    ],
)
async def test_each_failure_becomes_its_verdict_and_counts_as_an_attempt(result, verdict) -> None:
    world, _ = await scripted_world(lambda _: result)
    try:
        user, problem = await world.add_user(), await world.add_problem()
        outcome = await pipeline.judge_submission(world.deps, await world.add_submission(user, problem, "x"))
        assert outcome == verdict
        counted = await row(world, Problem, Problem.id == problem)
        assert (counted.total_submissions, counted.accepted_submissions) == (1, 0)
    finally:
        await world.close()


async def test_a_compilation_error_stores_the_compiler_output_and_runs_no_test() -> None:
    world, sandbox = await scripted_world(
        lambda _: exited("x"), compile_result=CompileResult(ok=False, output="main.cpp:1:1: error: nope")
    )
    try:
        user, problem = await world.add_user(), await world.add_problem()
        submission_id = await world.add_submission(user, problem, "int main(", language="cpp")
        assert await pipeline.judge_submission(world.deps, submission_id) == "COMPILATION_ERROR"
        result = await row(world, SubmissionResult, SubmissionResult.submission_id == submission_id)
        assert result.compile_output == "main.cpp:1:1: error: nope"
        assert sandbox.inputs == []
        saved = await row(world, Submission, Submission.id == submission_id)
        assert (saved.passed_count, saved.total_count) == (0, 3)
    finally:
        await world.close()


@pytest.mark.parametrize(
    "failure", [SandboxError("docker daemon unreachable at tcp://internal:2375"), RuntimeError("bug")]
)
async def test_a_judge_failure_is_system_error_and_is_not_an_attempt(failure) -> None:
    world, _ = await scripted_world(lambda _: exited(""), fail_on_open=failure)
    try:
        user, problem = await world.add_user(), await world.add_problem()
        submission_id = await world.add_submission(user, problem, "x")
        pubsub = await world.subscribe(user)
        assert await pipeline.judge_submission(world.deps, submission_id) == "failed"

        saved = await row(world, Submission, Submission.id == submission_id)
        assert (saved.status, saved.verdict) == ("FAILED", "SYSTEM_ERROR")
        assert saved.finished_at is not None
        counted = await row(world, Problem, Problem.id == problem)
        assert (counted.total_submissions, counted.accepted_submissions) == (0, 0)
        assert await row(world, UserProblemProgress, UserProblemProgress.user_id == user) is None

        seen = await drain(pubsub)
        assert [e["type"] for e in seen] == ["submission.running", "submission.failed"]
        blob = json.dumps(seen)
        assert "docker" not in blob
        assert "internal" not in blob  # infrastructure details never reach the client
    finally:
        await world.close()


async def test_a_language_without_a_runner_is_a_system_error() -> None:
    world, _ = await scripted_world(lambda _: exited(""))
    try:
        user, problem = await world.add_user(), await world.add_problem()
        submission_id = await world.add_submission(user, problem, "puts 1", language="ruby")
        assert await pipeline.judge_submission(world.deps, submission_id) == "failed"
        assert (await row(world, Submission, Submission.id == submission_id)).verdict == "SYSTEM_ERROR"
    finally:
        await world.close()


async def test_a_deleted_problem_fails_the_submission_instead_of_leaving_it_running() -> None:
    world, _ = await scripted_world(lambda _: exited(""))
    try:
        user, problem = await world.add_user(), await world.add_problem()
        submission_id = await world.add_submission(user, problem, "x")
        async with world.sessionmaker() as db:
            await db.execute(text("PRAGMA foreign_keys=OFF"))  # SQLite would otherwise cascade the submission away
            await db.execute(text("DELETE FROM problems"))
            await db.commit()
        assert await pipeline.judge_submission(world.deps, submission_id) == "failed"
        assert (await row(world, Submission, Submission.id == submission_id)).status == "FAILED"
    finally:
        await world.close()


# --- duplicate delivery -------------------------------------------------------------------------------------------------


async def test_a_redelivered_job_is_not_judged_twice() -> None:
    world, sandbox = await scripted_world(lambda stdin: exited(str(int(stdin) * 2) + "\n"))
    try:
        user, problem = await world.add_user(), await world.add_problem()
        submission_id = await world.add_submission(user, problem, "x")
        assert await pipeline.judge_submission(world.deps, submission_id) == "ACCEPTED"
        assert await pipeline.judge_submission(world.deps, submission_id) == "skipped"  # already COMPLETED
        assert sandbox.sessions_opened == 1
        counted = await row(world, Problem, Problem.id == problem)
        assert counted.total_submissions == 1  # counted once
    finally:
        await world.close()


async def test_unknown_submission_ids_are_skipped_quietly() -> None:
    world, sandbox = await scripted_world(lambda _: exited(""))
    try:
        assert await pipeline.judge_submission(world.deps, uuid.uuid4()) == "skipped"
        assert sandbox.sessions_opened == 0
    finally:
        await world.close()


# --- hidden tests never leak --------------------------------------------------------------------------------------------


async def test_no_hidden_data_reaches_events_or_storage() -> None:
    """Worst case: the program crashes on a hidden test and its stderr quotes the hidden input back."""

    def respond(stdin: str):
        if stdin.startswith(SECRET_INPUT):
            return exited("partial " + stdin, code=1, stderr="Traceback: bad input " + stdin)
        return exited("2\n")

    world, sandbox = await scripted_world(respond)
    try:
        user = await world.add_user()
        problem = await world.add_problem(
            tests=(("PUBLIC", "1\n", "2\n"), ("HIDDEN", SECRET_INPUT + "\n", SECRET_ANSWER + "\n"))
        )
        pubsub = await world.subscribe(user)
        submission_id = await world.add_submission(user, problem, "x", total=2)

        assert await pipeline.judge_submission(world.deps, submission_id) == "RUNTIME_ERROR"
        assert SECRET_INPUT + "\n" in sandbox.inputs  # the hidden test really was executed

        events_blob = json.dumps(await drain(pubsub))
        async with world.sessionmaker() as db:
            stored_rows = [
                [str(value) for value in record]
                for table in ("submissions", "submission_results", "submission_test_results")
                for record in (await db.execute(text(f"SELECT * FROM {table}"))).all()  # noqa: S608
            ]
        stored_blob = json.dumps(stored_rows)
        for blob in (events_blob, stored_blob):
            assert SECRET_INPUT not in blob
            assert SECRET_ANSWER not in blob
            assert "Traceback" not in blob  # nor the stderr of a hidden test
            assert "partial" not in blob  # nor its stdout
    finally:
        await world.close()


# --- Run ----------------------------------------------------------------------------------------------------------------


async def start_run(world: World, user: uuid.UUID, *, mode="samples", source=DOUBLE, stdin=None, slug="double") -> str:
    run_id = runs.new_run_id()
    await runs.create_run_record(
        world.redis,
        run_id,
        user_id=user,
        mode=mode,
        request={"problem_slug": slug, "language": "python", "source_code": source, "input": stdin},
        ttl_seconds=600,
    )
    return run_id


async def test_run_samples_uses_only_public_tests_and_shows_their_data(local_world: World) -> None:
    world = local_world
    user = await world.add_user()
    await world.add_problem(
        tests=(
            ("PUBLIC", "1\n", "2\n"),
            ("HIDDEN", SECRET_INPUT + "\n", SECRET_ANSWER + "\n"),
            ("HIDDEN", "5\n", "10\n"),
        )
    )
    pubsub = await world.subscribe(user)
    run_id = await start_run(world, user, source=WRONG)

    assert await pipeline.run_code(world.deps, run_id) == "WRONG_ANSWER"

    record = await runs.load_run_record(world.redis, run_id)
    assert record["status"] == "COMPLETED"
    assert "request" not in record  # the source is dropped once the run is over
    [case] = record["result"]["cases"]
    assert (case["input"], case["expected_output"], case["stdout"].strip(), case["verdict"]) == (
        "1\n",
        "2\n",
        "3",
        "WRONG_ANSWER",
    )
    assert SECRET_INPUT not in json.dumps(record)
    assert SECRET_ANSWER not in json.dumps(record)

    types = [e["type"] for e in await drain(pubsub)]
    assert types == ["run.running", "run.completed"]
    assert await row(world, Submission) is None  # not a submission
    assert (await row(world, Problem)).total_submissions == 0  # and not counted


async def test_run_samples_shows_every_example_even_after_a_failure(local_world: World) -> None:
    world = local_world
    user = await world.add_user()
    await world.add_problem(tests=(("PUBLIC", "1\n", "999\n"), ("PUBLIC", "2\n", "4\n"), ("HIDDEN", "3\n", "6\n")))
    run_id = await start_run(world, user)
    await pipeline.run_code(world.deps, run_id)
    cases = (await runs.load_run_record(world.redis, run_id))["result"]["cases"]
    assert [c["verdict"] for c in cases] == ["WRONG_ANSWER", "ACCEPTED"]


async def test_run_custom_input_returns_the_programs_output(local_world: World) -> None:
    world = local_world
    user = await world.add_user()
    await world.add_problem()
    run_id = await start_run(world, user, mode="custom", stdin="21\n")
    assert await pipeline.run_code(world.deps, run_id) == "OK"
    result = (await runs.load_run_record(world.redis, run_id))["result"]
    assert (result["outcome"], result["stdout"].strip(), result.get("cases")) == ("OK", "42", None)


async def test_run_custom_reports_runtime_errors_and_compile_errors(local_world: World) -> None:
    world = local_world
    user = await world.add_user()
    await world.add_problem()
    crash = await start_run(world, user, mode="custom", stdin="x\n")  # int("x") raises
    assert await pipeline.run_code(world.deps, crash) == "RUNTIME_ERROR"
    result = (await runs.load_run_record(world.redis, crash))["result"]
    assert "ValueError" in result["stderr"]  # a user's own crash output is theirs to see
    bad = await start_run(world, user, mode="custom", source="def (:\n", stdin="")
    assert await pipeline.run_code(world.deps, bad) == "COMPILATION_ERROR"


async def test_a_run_survives_being_delivered_twice(local_world: World) -> None:
    world = local_world
    user = await world.add_user()
    await world.add_problem()
    run_id = await start_run(world, user)
    assert await pipeline.run_code(world.deps, run_id) == "ACCEPTED"
    assert await pipeline.run_code(world.deps, run_id) == "skipped"
    assert await pipeline.run_code(world.deps, "does-not-exist-123456") == "skipped"


async def test_a_run_that_hits_a_sandbox_failure_fails_cleanly() -> None:
    world, _ = await scripted_world(lambda _: exited(""), fail_on_open=SandboxError("secret infra detail"))
    try:
        user = await world.add_user()
        await world.add_problem()
        pubsub = await world.subscribe(user)
        run_id = await start_run(world, user)
        assert await pipeline.run_code(world.deps, run_id) == "failed"
        record = await runs.load_run_record(world.redis, run_id)
        assert record["status"] == "FAILED"
        assert "secret infra detail" not in json.dumps(record)
        assert [e["type"] for e in await drain(pubsub)] == ["run.running", "run.failed"]
    finally:
        await world.close()


# --- reaper -------------------------------------------------------------------------------------------------------------


async def test_the_reaper_fails_only_stale_jobs_and_tells_their_owners() -> None:
    world, _ = await scripted_world(lambda _: exited(""))
    try:
        user, problem = await world.add_user(), await world.add_problem()
        old = await world.add_submission(user, problem, "x")
        fresh = await world.add_submission(user, problem, "x")
        judged = await world.add_submission(user, problem, "x")
        async with world.sessionmaker() as db:
            stale_time = utcnow() - timedelta(seconds=world.settings.judge_stale_after + 60)
            (await db.get(Submission, old)).created_at = stale_time
            done = await db.get(Submission, judged)
            done.created_at, done.status = stale_time, "COMPLETED"
            await db.commit()
        pubsub = await world.subscribe(user)

        assert await reaper.fail_stale_submissions(world.deps) == 1

        assert (await row(world, Submission, Submission.id == old)).status == "FAILED"
        assert (await row(world, Submission, Submission.id == old)).verdict == "SYSTEM_ERROR"
        assert (await row(world, Submission, Submission.id == fresh)).status == "QUEUED"
        assert (await row(world, Submission, Submission.id == judged)).status == "COMPLETED"
        assert (await row(world, Problem, Problem.id == problem)).total_submissions == 0
        [event] = await drain(pubsub)
        assert (event["type"], event["data"]["submission_id"]) == ("submission.failed", str(old))
        assert await reaper.fail_stale_submissions(world.deps) == 0  # idempotent
    finally:
        await world.close()
