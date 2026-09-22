"""Contests: visibility before/after start, registration, contest-scoped submit, and computed standings.

Judging itself is never exercised here (that's test_submissions_api.py/the judge suite) — standings tests seed
`Submission` rows directly, the same trick submissions tests use, since the queue is a recording double anyway.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from app.core.db import utcnow
from app.modules.contests.models import Contest, ContestParticipant, ContestProblem
from app.modules.submissions.models import Submission, SubmissionStatus, Verdict
from tests.conftest import RecordingQueue, create_user, make_client, signed_in
from tests.problems_helpers import HIDDEN_ANSWER, HIDDEN_SENTINEL, admin_session, insert_problem

FUTURE = utcnow() + timedelta(days=1)


async def seed_contest(
    app,
    slug: str = "spring-cup",
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    penalty_minutes: int = 20,
    problems: tuple[tuple[str, str, int], ...] = (),  # (problem_slug, label, points)
) -> uuid.UUID:
    start = start or (utcnow() + timedelta(hours=1))
    end = end or (start + timedelta(hours=2))
    async with app.state.sessionmaker() as db:
        from sqlalchemy import select

        from app.modules.problems.models import Problem

        contest = Contest(
            id=uuid.uuid4(), slug=slug, title=slug.title(), description="d",
            start_time=start, end_time=end, penalty_minutes=penalty_minutes, published=True,
        )  # fmt: skip
        rows = []
        for problem_slug, label, points in problems:
            problem_id = await db.scalar(select(Problem.id).where(Problem.slug == problem_slug))
            rows.append(ContestProblem(id=uuid.uuid4(), problem_id=problem_id, label=label, points=points))
        contest.problems = rows
        db.add(contest)
        await db.commit()
        return contest.id


async def register_user(app, contest_id: uuid.UUID, user_id: uuid.UUID) -> None:
    async with app.state.sessionmaker() as db:
        db.add(ContestParticipant(contest_id=contest_id, user_id=user_id, registered_at=utcnow()))
        await db.commit()


async def user_id_of(app, username: str) -> uuid.UUID:
    async with app.state.sessionmaker() as db:
        from sqlalchemy import select

        from app.modules.users.models import User

        return await db.scalar(select(User.id).where(User.username == username))


async def seed_submission(
    app, *, contest_id, user_id, problem_slug: str, verdict: str, created_at, status=SubmissionStatus.COMPLETED
) -> None:
    async with app.state.sessionmaker() as db:
        from sqlalchemy import select

        from app.modules.problems.models import Problem

        problem_id = await db.scalar(select(Problem.id).where(Problem.slug == problem_slug))
        db.add(
            Submission(
                id=uuid.uuid4(), user_id=user_id, problem_id=problem_id, language_key="python", source_code="x",
                status=status.value, verdict=verdict, contest_id=contest_id, created_at=created_at, total_count=1,
            )
        )  # fmt: skip
        await db.commit()


async def test_an_upcoming_contest_shows_no_problem_titles_and_is_not_registered_by_default(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum", published=False)
    contest_id = await seed_contest(app, problems=(("two-sum", "A", 100),))
    async with signed_in(app, username="ada") as (client, auth):
        response = await client.get("/api/contests/spring-cup", headers=auth)
    body = response.json()
    assert body["phase"] == "upcoming"
    assert body["problems"] == [{"label": "A", "points": 100, "title": None}]
    assert body["registered"] is False
    assert str(contest_id)  # sanity: the fixture actually ran


async def test_an_upcoming_contests_problem_is_not_reachable_by_anyone(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum", published=False)
    await seed_contest(app, problems=(("two-sum", "A", 100),))
    async with signed_in(app, username="ada") as (client, auth):
        response = await client.get("/api/contests/spring-cup/problems/A", headers=auth)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONTEST_PROBLEM_NOT_FOUND"


async def test_a_running_contests_problem_is_visible_to_anyone_signed_in_or_not_but_hides_hidden_tests(
    build_app,
) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum", title="Two Sum", published=False)
    await seed_contest(app, start=utcnow() - timedelta(minutes=1), problems=(("two-sum", "A", 100),))

    async with signed_in(app, username="ada") as (client, auth):
        detail = await client.get("/api/contests/spring-cup", headers=auth)
        problem = await client.get("/api/contests/spring-cup/problems/A", headers=auth)
    assert detail.json()["problems"] == [{"label": "A", "points": 100, "title": "Two Sum"}]
    assert problem.status_code == 200
    assert problem.json() == {"label": "A", "points": 100, "problem": problem.json()["problem"]}
    assert HIDDEN_SENTINEL not in problem.text and HIDDEN_ANSWER not in problem.text
    assert "test_case_id" not in problem.text and "is_public" not in problem.text

    async with make_client(app) as anon:
        spectator = await anon.get("/api/contests/spring-cup/problems/A")
    assert spectator.status_code == 200  # spectators can read; only submitting needs registration


async def test_an_ended_contests_problem_stays_readable_but_no_longer_accepts_submissions(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum", published=False)
    await seed_contest(
        app, start=utcnow() - timedelta(hours=2), end=utcnow() - timedelta(hours=1), problems=(("two-sum", "A", 100),)
    )
    async with signed_in(app, username="ada") as (client, auth):
        problem = await client.get("/api/contests/spring-cup/problems/A", headers=auth)
        submit = await client.post(
            "/api/contests/spring-cup/problems/A/submit",
            json={"language": "python", "source_code": "print(1)\n"},
            headers=auth,
        )
    assert problem.status_code == 200
    assert (submit.status_code, submit.json()["error"]["code"]) == (409, "CONTEST_ENDED")


async def test_registration_is_idempotent_and_closes_when_the_contest_ends(build_app) -> None:
    app = await build_app()
    await seed_contest(app, "open-cup", start=utcnow() + timedelta(hours=1))
    await seed_contest(app, "past-cup", start=utcnow() - timedelta(hours=2), end=utcnow() - timedelta(hours=1))
    async with signed_in(app, username="ada") as (client, auth):
        first = await client.post("/api/contests/open-cup/register", headers=auth)
        second = await client.post("/api/contests/open-cup/register", headers=auth)
        closed = await client.post("/api/contests/past-cup/register", headers=auth)
        detail = await client.get("/api/contests/open-cup", headers=auth)
    assert first.status_code == second.status_code == 204
    assert (closed.status_code, closed.json()["error"]["code"]) == (409, "CONTEST_ENDED")
    assert detail.json()["registered"] is True


async def test_submitting_requires_registration_and_tags_the_submission_with_the_contest(build_app) -> None:
    queue = RecordingQueue()
    app = await build_app(queue=queue)
    await insert_problem(app, "two-sum", published=False)
    contest_id = await seed_contest(app, start=utcnow() - timedelta(minutes=1), problems=(("two-sum", "A", 100),))

    async with signed_in(app, username="ada") as (client, auth):
        refused = await client.post(
            "/api/contests/spring-cup/problems/A/submit",
            json={"language": "python", "source_code": "print(1)\n"},
            headers=auth,
        )
        assert (refused.status_code, refused.json()["error"]["code"]) == (403, "NOT_REGISTERED")

        await client.post("/api/contests/spring-cup/register", headers=auth)
        submitted = await client.post(
            "/api/contests/spring-cup/problems/A/submit",
            json={"language": "python", "source_code": "print(1)\n"},
            headers=auth,
        )
    assert submitted.status_code == 202
    assert queue.jobs and queue.jobs[0][0] == "sahujudge.judge_submission"

    async with app.state.sessionmaker() as db:
        submission = await db.get(Submission, uuid.UUID(submitted.json()["id"]))
    assert submission.contest_id == contest_id
    assert submission.source_code == "print(1)\n"


async def test_submitting_to_a_problem_not_in_the_contest_is_a_404(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum", published=False)
    await seed_contest(app, start=utcnow() - timedelta(minutes=1), problems=(("two-sum", "A", 100),))
    async with signed_in(app, username="ada") as (client, auth):
        await client.post("/api/contests/spring-cup/register", headers=auth)
        response = await client.post(
            "/api/contests/spring-cup/problems/Z/submit",
            json={"language": "python", "source_code": "print(1)\n"},
            headers=auth,
        )
    assert response.status_code == 404


async def test_an_unpublished_contest_is_invisible_and_a_missing_slug_is_the_same_404(build_app) -> None:
    app = await build_app()
    async with app.state.sessionmaker() as db:
        db.add(
            Contest(id=uuid.uuid4(), slug="draft-cup", title="t", start_time=FUTURE, end_time=FUTURE, published=False)
        )
        await db.commit()
    async with signed_in(app, username="ada") as (client, auth):
        draft = await client.get("/api/contests/draft-cup", headers=auth)
        missing = await client.get("/api/contests/does-not-exist", headers=auth)
        empty = await client.get("/api/contests", headers=auth)
    assert draft.status_code == missing.status_code == 404
    assert draft.json()["error"]["code"] == missing.json()["error"]["code"] == "CONTEST_NOT_FOUND"
    assert empty.json() == []


# --- standings -------------------------------------------------------------------------------------------------------


async def test_standings_rank_by_points_then_penalty_then_who_finished_first(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "a-prob", published=False)
    await insert_problem(app, "b-prob", published=False)
    start = utcnow() - timedelta(hours=1)
    contest_id = await seed_contest(
        app, start=start, end=start + timedelta(hours=3), penalty_minutes=20,
        problems=(("a-prob", "A", 100), ("b-prob", "B", 100)),
    )  # fmt: skip

    for username in ("ada", "bob", "cleo"):
        await create_user(app, email=f"{username}@example.com", username=username)
    ada = await user_id_of(app, "ada")
    bob = await user_id_of(app, "bob")
    cleo = await user_id_of(app, "cleo")
    for uid in (ada, bob, cleo):
        await register_user(app, contest_id, uid)

    # ada: solves A at +10min with one prior wrong answer (penalty 10 + 20 = 30), never attempts B.
    await seed_submission(
        app,
        contest_id=contest_id,
        user_id=ada,
        problem_slug="a-prob",
        verdict=Verdict.WRONG_ANSWER.value,
        created_at=start + timedelta(minutes=5),
    )
    await seed_submission(
        app,
        contest_id=contest_id,
        user_id=ada,
        problem_slug="a-prob",
        verdict=Verdict.ACCEPTED.value,
        created_at=start + timedelta(minutes=10),
    )
    # bob: solves A cleanly at +40min (penalty 40) — same points as ada, worse penalty.
    await seed_submission(
        app,
        contest_id=contest_id,
        user_id=bob,
        problem_slug="a-prob",
        verdict=Verdict.ACCEPTED.value,
        created_at=start + timedelta(minutes=40),
    )
    # cleo: solves both A (+5min) and B (+15min) — more points than either.
    await seed_submission(
        app,
        contest_id=contest_id,
        user_id=cleo,
        problem_slug="a-prob",
        verdict=Verdict.ACCEPTED.value,
        created_at=start + timedelta(minutes=5),
    )
    await seed_submission(
        app,
        contest_id=contest_id,
        user_id=cleo,
        problem_slug="b-prob",
        verdict=Verdict.ACCEPTED.value,
        created_at=start + timedelta(minutes=15),
    )
    # A SYSTEM_ERROR and a COMPILATION_ERROR must never count as attempts or affect anything.
    await seed_submission(
        app,
        contest_id=contest_id,
        user_id=bob,
        problem_slug="a-prob",
        verdict=Verdict.SYSTEM_ERROR.value,
        created_at=start + timedelta(minutes=1),
    )
    await seed_submission(
        app,
        contest_id=contest_id,
        user_id=bob,
        problem_slug="a-prob",
        verdict=Verdict.COMPILATION_ERROR.value,
        created_at=start + timedelta(minutes=2),
    )
    # A still-QUEUED submission (no verdict yet) must never count either.
    await seed_submission(
        app, contest_id=contest_id, user_id=cleo, problem_slug="b-prob", verdict=None,
        created_at=start + timedelta(minutes=20), status=SubmissionStatus.QUEUED,
    )  # fmt: skip

    async with make_client(app) as client:
        response = await client.get("/api/contests/spring-cup/standings")
    body = response.json()
    assert [row["username"] for row in body["rows"]] == ["cleo", "ada", "bob"]
    assert [row["total_points"] for row in body["rows"]] == [200, 100, 100]
    assert body["rows"][1]["total_penalty_minutes"] == 30  # ada
    assert body["rows"][1]["cells"]["A"] == {"solved": True, "attempts": 1, "penalty_minutes": 30}
    assert body["rows"][1]["cells"]["B"] == {"solved": False, "attempts": 0, "penalty_minutes": 0}
    assert body["rows"][2]["total_penalty_minutes"] == 40  # bob: SYSTEM_ERROR/COMPILATION_ERROR did not add penalty
    assert body["rows"][2]["cells"]["A"] == {"solved": True, "attempts": 0, "penalty_minutes": 40}
    assert [row["rank"] for row in body["rows"]] == [1, 2, 3]


async def test_a_solve_outside_the_contest_window_is_never_counted(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "a-prob", published=False)
    start = utcnow() - timedelta(hours=1)
    contest_id = await seed_contest(app, start=start, end=start + timedelta(hours=2), problems=(("a-prob", "A", 100),))
    await create_user(app)  # "ada" (the default)
    ada = await user_id_of(app, "ada")
    await register_user(app, contest_id, ada)
    await seed_submission(
        app,
        contest_id=contest_id,
        user_id=ada,
        problem_slug="a-prob",
        verdict=Verdict.ACCEPTED.value,
        created_at=start - timedelta(minutes=5),
    )
    async with make_client(app) as client:
        response = await client.get("/api/contests/spring-cup/standings")
    assert response.json()["rows"][0]["total_points"] == 0


async def test_registered_participants_with_no_submissions_still_appear(build_app) -> None:
    app = await build_app()
    contest_id = await seed_contest(app, start=utcnow() - timedelta(minutes=1))
    await create_user(app)  # "ada" (the default)
    await register_user(app, contest_id, await user_id_of(app, "ada"))
    async with make_client(app) as client:
        response = await client.get("/api/contests/spring-cup/standings")
    assert response.json()["rows"] == [
        {"rank": 1, "username": "ada", "total_points": 0, "total_penalty_minutes": 0, "cells": {}}
    ]


# --- admin --------------------------------------------------------------------------------------------------------


def contest_payload(**overrides):
    body = {
        "slug": "spring-cup",
        "title": "Spring Cup",
        "description": "A friendly contest.",
        "start_time": FUTURE.isoformat(),
        "end_time": (FUTURE + timedelta(hours=2)).isoformat(),
        "penalty_minutes": 20,
        "problems": [],
    }
    body.update(overrides)
    return body


async def test_only_an_admin_may_manage_contests(build_app) -> None:
    app = await build_app()
    async with signed_in(app, username="ada") as (client, auth):
        response = await client.post("/api/admin/contests", json=contest_payload(), headers=auth)
    assert response.status_code == 403


async def test_admin_creates_edits_and_publishes_a_contest(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum", published=False)
    async with admin_session(app) as (client, auth):
        created = await client.post(
            "/api/admin/contests",
            json=contest_payload(problems=[{"problem_slug": "two-sum", "label": "A", "points": 250}]),
            headers=auth,
        )
        assert created.status_code == 201
        body = created.json()
        assert body["published"] is False
        assert body["problems"] == [
            {"label": "A", "points": 250, "problem_slug": "two-sum", "problem_title": "Two Sum"}
        ]

        published = await client.post(f"/api/admin/contests/{body['id']}/publish", headers=auth)
        assert published.json()["published"] is True

        updated = await client.put(
            f"/api/admin/contests/{body['id']}",
            json=contest_payload(
                title="Spring Cup 2", problems=[{"problem_slug": "two-sum", "label": "A", "points": 300}]
            ),
            headers=auth,
        )
        assert updated.status_code == 200
        assert updated.json()["title"] == "Spring Cup 2"
        assert updated.json()["problems"][0]["points"] == 300

    async with signed_in(app, username="ada") as (client, auth):
        listed = await client.get("/api/contests", headers=auth)
    assert [c["slug"] for c in listed.json()] == ["spring-cup"]


async def test_publishing_an_empty_contest_is_refused(build_app) -> None:
    app = await build_app()
    async with admin_session(app) as (client, auth):
        created = await client.post("/api/admin/contests", json=contest_payload(), headers=auth)
        published = await client.post(f"/api/admin/contests/{created.json()['id']}/publish", headers=auth)
    assert (published.status_code, published.json()["error"]["code"]) == (422, "CONTEST_NOT_READY")


async def test_a_contest_cannot_be_edited_once_it_has_started(build_app) -> None:
    app = await build_app()
    async with admin_session(app) as (client, auth):
        created = await client.post(
            "/api/admin/contests",
            json=contest_payload(start_time=(utcnow() - timedelta(minutes=1)).isoformat()),
            headers=auth,
        )
        response = await client.put(
            f"/api/admin/contests/{created.json()['id']}", json=contest_payload(title="x"), headers=auth
        )
    assert (response.status_code, response.json()["error"]["code"]) == (409, "CONTEST_ALREADY_STARTED")


async def test_referencing_an_unknown_problem_or_duplicate_label_is_rejected(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum", published=False)
    async with admin_session(app) as (client, auth):
        unknown = await client.post(
            "/api/admin/contests",
            json=contest_payload(problems=[{"problem_slug": "no-such-problem", "label": "A", "points": 100}]),
            headers=auth,
        )
        duplicate = await client.post(
            "/api/admin/contests",
            json=contest_payload(
                slug="other-cup",
                problems=[
                    {"problem_slug": "two-sum", "label": "A", "points": 100},
                    {"problem_slug": "two-sum", "label": "B", "points": 50},
                ],
            ),
            headers=auth,
        )
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (422, "PROBLEM_NOT_FOUND")
    assert duplicate.status_code == 422  # the same problem twice — rejected by the schema validator


async def test_a_duplicate_slug_is_rejected(build_app) -> None:
    app = await build_app()
    async with admin_session(app) as (client, auth):
        await client.post("/api/admin/contests", json=contest_payload(), headers=auth)
        clash = await client.post("/api/admin/contests", json=contest_payload(), headers=auth)
    assert (clash.status_code, clash.json()["error"]["code"]) == (409, "SLUG_TAKEN")


# --- run (custom-input test, same access rule as submit) -----------------------------------------------------------


async def test_running_a_contest_problem_needs_registration_and_enqueues_like_the_plain_run_endpoint(build_app) -> None:
    queue = RecordingQueue()
    app = await build_app(queue=queue)
    await insert_problem(app, "two-sum", published=False)
    await seed_contest(app, start=utcnow() - timedelta(minutes=1), problems=(("two-sum", "A", 100),))

    async with signed_in(app, username="ada") as (client, auth):
        refused = await client.post(
            "/api/contests/spring-cup/problems/A/run",
            json={"language": "python", "source_code": "print(1)\n", "mode": "custom", "input": "1\n"},
            headers=auth,
        )
        assert (refused.status_code, refused.json()["error"]["code"]) == (403, "NOT_REGISTERED")

        await client.post("/api/contests/spring-cup/register", headers=auth)
        run = await client.post(
            "/api/contests/spring-cup/problems/A/run",
            json={"language": "python", "source_code": "print(1)\n", "mode": "custom", "input": "1\n"},
            headers=auth,
        )
    assert run.status_code == 202
    assert run.json()["status"] == "QUEUED"
    assert queue.jobs and queue.jobs[0][0] == "sahujudge.run_code"


async def test_running_a_contest_problem_before_it_starts_is_a_404(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum", published=False)
    await seed_contest(app, problems=(("two-sum", "A", 100),))
    async with signed_in(app, username="ada") as (client, auth):
        response = await client.post(
            "/api/contests/spring-cup/problems/A/run",
            json={"language": "python", "source_code": "print(1)\n"},
            headers=auth,
        )
    assert response.status_code == 404
