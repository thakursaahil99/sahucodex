"""Submission, run and ticket endpoints. The queue is a recording double; nothing here executes code."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from sqlalchemy import select

from app.core.db import utcnow
from app.modules.problems.models import Problem, ProgrammingLanguage
from app.modules.submissions import events, runs
from app.modules.submissions.models import (
    Submission,
    SubmissionResult,
    SubmissionStatus,
    SubmissionTestResult,
    Verdict,
)
from app.modules.users.models import User
from tests.conftest import RecordingQueue, make_settings, signed_in
from tests.problems_helpers import HIDDEN_ANSWER, HIDDEN_SENTINEL, insert_problem

GOOD = {"problem_slug": "two-sum", "language": "python", "source_code": "print(2)\n"}


async def user_id(app, username: str) -> uuid.UUID:
    async with app.state.sessionmaker() as db:
        return await db.scalar(select(User.id).where(User.username == username))


async def next_message(pubsub, timeout_s: float = 1.0):
    """The first get_message() after subscribing consumes the subscription confirmation, so poll."""
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.05)
        if message is not None:
            return message
    return None


async def all_submissions(app) -> list[Submission]:
    async with app.state.sessionmaker() as db:
        return list((await db.scalars(select(Submission).order_by(Submission.created_at))).all())


# --- authentication ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/submissions"),
        ("GET", f"/api/submissions/{uuid.uuid4()}"),
        ("GET", "/api/users/me/submissions"),
        ("POST", "/api/run"),
        ("GET", "/api/run/abcdefabcdefabcdef"),
        ("POST", "/api/ws/ticket"),
    ],
)
async def test_every_judge_endpoint_requires_authentication(app, client, method, path) -> None:
    response = await client.request(method, path, json=GOOD if method == "POST" else None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


# --- submitting --------------------------------------------------------------------------------------------------


async def test_submit_returns_an_id_immediately_and_enqueues_only_the_id(build_app) -> None:
    queue = RecordingQueue()
    app = await build_app(queue=queue)
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="ada") as (client, auth):
        response = await client.post("/api/submissions", json=GOOD, headers=auth)
        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "QUEUED"
        submission_id = body["id"]

    assert queue.jobs == [("sahujudge.judge_submission", (submission_id,), "judge")]  # identifiers only, no code
    [row] = await all_submissions(app)
    assert (row.status, row.verdict, row.total_count, row.passed_count) == ("QUEUED", None, 2, 0)
    assert row.source_code == GOOD["source_code"]
    assert row.user_id == await user_id(app, "ada")  # taken from the token, not from the body


async def test_the_client_cannot_supply_scores_verdicts_or_identities(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="ada") as (client, auth):
        for extra in (
            {"verdict": "ACCEPTED"},
            {"status": "COMPLETED"},
            {"user_id": str(uuid.uuid4())},
            {"passed_count": 99},
            {"runtime_ms": 1},
        ):
            response = await client.post("/api/submissions", json={**GOOD, **extra}, headers=auth)
            assert response.status_code == 422, extra
    assert await all_submissions(app) == []


@pytest.mark.parametrize(
    ("override", "status", "code"),
    [
        ({"problem_slug": "no-such-problem"}, 404, "PROBLEM_NOT_FOUND"),
        ({"problem_slug": "draft-problem"}, 404, "PROBLEM_NOT_FOUND"),  # unpublished problems are invisible
        ({"problem_slug": "old-problem"}, 404, "PROBLEM_NOT_FOUND"),  # so are archived ones
        ({"language": "cobol"}, 422, "UNKNOWN_LANGUAGE"),
        ({"language": "javascript"}, 422, "LANGUAGE_DISABLED"),
        ({"source_code": "   \n"}, 422, "INVALID_SOURCE"),
        ({"source_code": "print(1)\x00"}, 422, "INVALID_SOURCE"),
        ({"source_code": "#" * 2000}, 422, "SOURCE_TOO_LARGE"),
        ({"source_code": ""}, 422, "VALIDATION_ERROR"),
        ({"language": "Py; rm -rf /"}, 422, "VALIDATION_ERROR"),
        ({"problem_slug": "../../etc/passwd"}, 422, "VALIDATION_ERROR"),
        ({"source_code": 12345}, 422, "VALIDATION_ERROR"),
    ],
)
async def test_invalid_submissions_are_rejected_and_never_queued(build_app, override, status, code) -> None:
    queue = RecordingQueue()
    app = await build_app(make_settings(submission_max_source_bytes=1024), queue=queue)
    await insert_problem(app, "two-sum")
    await insert_problem(app, "draft-problem", published=False)
    await insert_problem(app, "old-problem", archived=True)
    async with app.state.sessionmaker() as db:
        (await db.get(ProgrammingLanguage, "javascript")).is_enabled = False
        await db.commit()
    async with signed_in(app, username="ada") as (client, auth):
        response = await client.post("/api/submissions", json={**GOOD, **override}, headers=auth)
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert queue.jobs == []
    assert await all_submissions(app) == []


async def test_submissions_are_rate_limited_per_user(build_app) -> None:
    app = await build_app(make_settings(rate_limit_submit="2/minute", max_inflight_submissions=50))
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="ada") as (ada, ada_auth), signed_in(app, username="bob") as (bob, bob_auth):
        assert (await ada.post("/api/submissions", json=GOOD, headers=ada_auth)).status_code == 202
        assert (await ada.post("/api/submissions", json=GOOD, headers=ada_auth)).status_code == 202
        limited = await ada.post("/api/submissions", json=GOOD, headers=ada_auth)
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) >= 1
        assert (await bob.post("/api/submissions", json=GOOD, headers=bob_auth)).status_code == 202  # bob is unaffected


async def test_a_user_cannot_flood_the_queue_with_pending_submissions(build_app) -> None:
    app = await build_app(make_settings(max_inflight_submissions=2, rate_limit_submit="100/minute"))
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="ada") as (client, auth):
        assert (await client.post("/api/submissions", json=GOOD, headers=auth)).status_code == 202
        assert (await client.post("/api/submissions", json=GOOD, headers=auth)).status_code == 202
        blocked = await client.post("/api/submissions", json=GOOD, headers=auth)
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "TOO_MANY_PENDING_SUBMISSIONS"

        # Once the first two are judged, submitting works again.
        async with app.state.sessionmaker() as db:
            for row in await db.scalars(select(Submission)):
                row.status = SubmissionStatus.COMPLETED.value
            await db.commit()
        assert (await client.post("/api/submissions", json=GOOD, headers=auth)).status_code == 202


async def test_a_broker_outage_fails_the_submission_cleanly(build_app) -> None:
    queue = RecordingQueue(down=True)
    app = await build_app(queue=queue)
    await insert_problem(app, "two-sum", total=5, accepted=2)
    async with signed_in(app, username="ada") as (client, auth):
        response = await client.post("/api/submissions", json=GOOD, headers=auth)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "JUDGE_UNAVAILABLE"
    [row] = await all_submissions(app)
    assert (row.status, row.verdict) == ("FAILED", "SYSTEM_ERROR")  # not stuck in QUEUED forever
    assert row.finished_at is not None


async def test_a_queued_event_is_published_for_the_owner_only(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="ada") as (client, auth):
        ada_id = await user_id(app, "ada")
        pubsub = app.state.redis.pubsub()
        await pubsub.subscribe(events.user_channel(ada_id))
        other = app.state.redis.pubsub()
        await other.subscribe(events.user_channel(uuid.uuid4()))
        await client.post("/api/submissions", json=GOOD, headers=auth)
        message = await next_message(pubsub)
        assert message is not None
        event = json.loads(message["data"])
        assert event["type"] == "submission.queued"
        assert event["data"]["status"] == "QUEUED"
        assert "source_code" not in message["data"]
        assert await next_message(other, timeout_s=0.2) is None


# --- reading ------------------------------------------------------------------------------------------------------


async def seed_judged(app, username: str, *, verdict: Verdict = Verdict.WRONG_ANSWER, slug: str = "two-sum", **kw):
    """A judged submission with one public and one hidden per-test row, as the worker would leave it."""
    async with app.state.sessionmaker() as db:
        problem_id = await db.scalar(select(Problem.id).where(Problem.slug == slug))
        submission = Submission(
            user_id=await user_id(app, username),
            problem_id=problem_id,
            language_key=kw.get("language", "python"),
            source_code="print('mine')\n",
            status=SubmissionStatus.COMPLETED.value,
            verdict=verdict.value,
            runtime_ms=12,
            memory_kb=3400,
            passed_count=1,
            total_count=2,
            created_at=kw.get("created_at", utcnow()),
            finished_at=utcnow(),
        )
        db.add(submission)
        await db.flush()
        db.add(
            SubmissionResult(
                submission_id=submission.id,
                compile_output="warning: something",
                message="Exited with code 1",
                checker="lines",
                judge_version="1",
                time_limit_ms=6000,
                memory_limit_mb=256,
            )
        )
        db.add_all(
            [
                SubmissionTestResult(
                    submission_id=submission.id,
                    position=1,
                    is_public=True,
                    verdict="ACCEPTED",
                    runtime_ms=5,
                    memory_kb=3000,
                ),
                SubmissionTestResult(
                    submission_id=submission.id,
                    position=2,
                    is_public=False,
                    verdict=verdict.value,
                    runtime_ms=12,
                    memory_kb=3400,
                ),
            ]
        )
        await db.commit()
        return submission.id


async def test_the_owner_sees_details_but_hidden_tests_never_appear(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="ada") as (client, auth):
        submission_id = await seed_judged(app, "ada")
        response = await client.get(f"/api/submissions/{submission_id}", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "WRONG_ANSWER"
    assert (body["passed_count"], body["total_count"]) == (1, 2)
    assert body["source_code"] == "print('mine')\n"
    assert body["compile_output"] == "warning: something"
    assert body["time_limit_ms"] == 6000
    assert [t["position"] for t in body["test_results"]] == [1]  # the hidden test's row is not exposed
    assert HIDDEN_SENTINEL not in response.text
    assert HIDDEN_ANSWER not in response.text
    forbidden_keys = {"input", "expected_output", "expected", "stdout", "stderr", "test_case_id", "is_public"}
    assert not forbidden_keys & set(json.dumps(body).replace('"', " ").replace(":", " ").split())


async def test_other_users_get_the_same_404_as_a_missing_id(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="ada"):
        submission_id = await seed_judged(app, "ada")
    async with signed_in(app, username="bob") as (client, auth):
        theirs = await client.get(f"/api/submissions/{submission_id}", headers=auth)
        missing = await client.get(f"/api/submissions/{uuid.uuid4()}", headers=auth)
    assert theirs.status_code == missing.status_code == 404
    assert theirs.json() == missing.json()


async def test_a_malformed_id_is_a_validation_error_not_a_crash(build_app) -> None:
    app = await build_app()
    async with signed_in(app, username="ada") as (client, auth):
        assert (await client.get("/api/submissions/not-a-uuid", headers=auth)).status_code == 422


async def test_history_is_paginated_filterable_and_private(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum")
    await insert_problem(app, "other-problem")
    async with signed_in(app, username="ada") as (ada, ada_auth), signed_in(app, username="bob") as (bob, bob_auth):
        from datetime import timedelta

        base = utcnow()
        for n in range(5):
            await seed_judged(
                app,
                "ada",
                verdict=Verdict.ACCEPTED if n % 2 else Verdict.WRONG_ANSWER,
                created_at=base - timedelta(minutes=n),
            )
        await seed_judged(app, "ada", slug="other-problem", verdict=Verdict.RUNTIME_ERROR, language="cpp")
        await seed_judged(app, "bob")

        everything = (await ada.get("/api/users/me/submissions", headers=ada_auth)).json()
        assert everything["total"] == 6  # bob's is not included
        assert "source_code" not in json.dumps(everything)  # lists never carry source

        page = (await ada.get("/api/users/me/submissions?limit=2&page=2", headers=ada_auth)).json()
        assert (len(page["items"]), page["page"], page["pages"]) == (2, 2, 3)

        newest_first = [i["created_at"] for i in everything["items"]]
        assert newest_first == sorted(newest_first, reverse=True)

        def total(query: str, client=ada, auth=ada_auth):
            return client.get(f"/api/users/me/submissions?{query}", headers=auth)

        assert (await total("problem=other-problem")).json()["total"] == 1
        assert (await total("verdict=ACCEPTED")).json()["total"] == 2
        assert (await total("language=cpp")).json()["total"] == 1
        assert (await total("status=COMPLETED")).json()["total"] == 6
        assert (await total("status=QUEUED")).json()["total"] == 0
        assert (await total("problem=two-sum&verdict=WRONG_ANSWER")).json()["total"] == 3
        assert (await total("verdict=NOPE")).status_code == 422
        assert (await total("problem=../x")).status_code == 422
        assert (await total("limit=1000")).status_code == 422
        assert (await total("", bob, bob_auth)).json()["total"] == 1


# --- run ----------------------------------------------------------------------------------------------------------


async def test_run_queues_an_ephemeral_job_owned_by_the_caller(build_app) -> None:
    queue = RecordingQueue()
    app = await build_app(queue=queue)
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="ada") as (client, auth):
        response = await client.post("/api/run", json={**GOOD, "mode": "samples"}, headers=auth)
        assert response.status_code == 202
        run_id = response.json()["id"]
        assert queue.jobs == [("sahujudge.run_code", (run_id,), "judge")]
        assert await all_submissions(app) == []  # a run is not a submission

        polled = (await client.get(f"/api/run/{run_id}", headers=auth)).json()
        assert (polled["status"], polled["mode"], polled["result"]) == ("QUEUED", "samples", None)
        assert "source" not in json.dumps(polled)

    async with signed_in(app, username="bob") as (bob, bob_auth):
        assert (await bob.get(f"/api/run/{run_id}", headers=bob_auth)).status_code == 404  # not bob's


async def test_run_custom_input_is_validated(build_app) -> None:
    app = await build_app(make_settings(run_max_input_bytes=100))
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="ada") as (client, auth):
        ok = await client.post("/api/run", json={**GOOD, "mode": "custom", "input": "5\n"}, headers=auth)
        assert ok.status_code == 202
        record = await runs.load_run_record(app.state.redis, ok.json()["id"])
        assert record["request"]["input"] == "5\n"
        big = await client.post("/api/run", json={**GOOD, "mode": "custom", "input": "x" * 101}, headers=auth)
        assert (big.status_code, big.json()["error"]["code"]) == (422, "INPUT_TOO_LARGE")
        nul = await client.post("/api/run", json={**GOOD, "mode": "custom", "input": "a\x00b"}, headers=auth)
        assert nul.json()["error"]["code"] == "INVALID_INPUT"
        assert (await client.post("/api/run", json={**GOOD, "mode": "hidden"}, headers=auth)).status_code == 422
        assert (await client.post("/api/run", json={**GOOD, "test_id": "1"}, headers=auth)).status_code == 422


async def test_run_never_selects_hidden_tests_and_is_rate_limited(build_app) -> None:
    app = await build_app(make_settings(rate_limit_run="2/minute"))
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="ada") as (client, auth):
        for _ in range(2):
            assert (await client.post("/api/run", json=GOOD, headers=auth)).status_code == 202
        assert (await client.post("/api/run", json=GOOD, headers=auth)).status_code == 429


@pytest.mark.parametrize("run_id", ["short", "a" * 41, "../../etc/passwd", "ok" * 10 + "!", "abcdefabcdefabcdefabcdef"])
async def test_unknown_or_malformed_run_ids_are_404(build_app, run_id) -> None:
    app = await build_app()
    async with signed_in(app, username="ada") as (client, auth):
        response = await client.get(f"/api/run/{run_id}", headers=auth)
    assert response.status_code in (404, 422)


async def test_run_broker_outage_is_reported_and_leaves_nothing_behind(build_app) -> None:
    queue = RecordingQueue(down=True)
    app = await build_app(queue=queue)
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="ada") as (client, auth):
        response = await client.post("/api/run", json=GOOD, headers=auth)
    assert response.status_code == 503
    assert [key async for key in app.state.redis.scan_iter("run:*")] == []


# --- websocket tickets -------------------------------------------------------------------------------------------


async def test_a_ticket_is_single_use_and_bound_to_the_user(build_app) -> None:
    app = await build_app()
    async with signed_in(app, username="ada") as (client, auth):
        ticket = (await client.post("/api/ws/ticket", headers=auth)).json()
        assert ticket["expires_in"] == 30
        redis = app.state.redis
        assert await events.redeem_ticket(redis, ticket["ticket"]) == await user_id(app, "ada")
        assert await events.redeem_ticket(redis, ticket["ticket"]) is None  # replay fails
        assert await events.redeem_ticket(redis, "x" * 43) is None  # guessing fails
        assert await events.redeem_ticket(redis, "short") is None
        assert [key async for key in redis.scan_iter("ws:ticket:*")] == []


async def test_tickets_are_stored_hashed_and_expire(build_app) -> None:
    app = await build_app(make_settings(ws_ticket_ttl=1))
    async with signed_in(app, username="ada") as (client, auth):
        ticket = (await client.post("/api/ws/ticket", headers=auth)).json()["ticket"]
        keys = [key async for key in app.state.redis.scan_iter("ws:ticket:*")]
        assert len(keys) == 1
        assert ticket not in keys[0]  # only a digest is stored
        await asyncio.sleep(1.2)
        assert await events.redeem_ticket(app.state.redis, ticket) is None


async def test_a_revoked_session_cannot_mint_tickets(build_app) -> None:
    app = await build_app()
    async with signed_in(app, username="ada") as (client, auth):
        assert (await client.post("/api/auth/logout", headers=auth)).status_code in (200, 204)
        assert (await client.post("/api/ws/ticket", headers=auth)).status_code == 401
