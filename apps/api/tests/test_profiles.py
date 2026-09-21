"""GET /api/users/{username}/stats: solved counts, streak, achievements, activity calendar."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.db import utcnow
from app.modules.profiles.achievements import CATALOG
from app.modules.profiles.models import Achievement, UserAchievement, UserStreak
from app.modules.submissions.models import Submission, SubmissionStatus, Verdict
from app.modules.users.models import User
from tests.conftest import create_user, make_client
from tests.problems_helpers import insert_problem, set_progress


async def user_id(app, username: str) -> uuid.UUID:
    async with app.state.sessionmaker() as db:
        return await db.scalar(select(User.id).where(User.username == username))


async def add_submission(
    app, uid: uuid.UUID, problem_id: uuid.UUID, verdict: str, *, language: str = "python", when=None
) -> None:
    async with app.state.sessionmaker() as db:
        db.add(
            Submission(
                user_id=uid,
                problem_id=problem_id,
                language_key=language,
                source_code="x",
                status=SubmissionStatus.COMPLETED.value,
                verdict=verdict,
                total_count=1,
                passed_count=1 if verdict == Verdict.ACCEPTED.value else 0,
                created_at=when or utcnow(),
            )
        )
        await db.commit()


async def test_stats_for_a_fresh_user_are_all_zero_and_every_achievement_is_locked(app):
    await create_user(app, email="fresh@example.com", username="fresh")
    async with make_client(app) as client:
        response = await client.get("/api/users/fresh/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["solved"] == {"easy": 0, "medium": 0, "hard": 0, "total": 0}
    assert (body["total_submissions"], body["accepted_submissions"], body["acceptance_rate"]) == (0, 0, None)
    assert body["streak"] == {"current": 0, "longest": 0, "last_active_date": None}
    assert body["activity"] == []
    assert len(body["achievements"]) == len(CATALOG)
    assert all(a["earned"] is False and a["earned_at"] is None for a in body["achievements"])


async def test_stats_do_not_require_authentication(app):
    await create_user(app, email="pub@example.com", username="pub")
    async with make_client(app) as client:
        assert (await client.get("/api/users/pub/stats")).status_code == 200


async def test_stats_404_for_an_unknown_or_inactive_user_like_the_public_profile(app):
    await create_user(app, email="gone@example.com", username="disabled_user")
    async with app.state.sessionmaker() as db:
        (await db.scalar(select(User).where(User.username == "disabled_user"))).is_active = False
        await db.commit()
    async with make_client(app) as client:
        missing = await client.get("/api/users/no-such-user/stats")
        disabled = await client.get("/api/users/disabled_user/stats")
    assert missing.status_code == disabled.status_code == 404
    assert missing.json()["error"]["code"] == "USER_NOT_FOUND"


async def test_stats_count_solved_problems_by_difficulty(app):
    await create_user(app, email="ada@example.com", username="ada")
    easy1 = await insert_problem(app, "easy-one", difficulty="EASY")
    easy2 = await insert_problem(app, "easy-two", difficulty="EASY")
    hard = await insert_problem(app, "hard-one", difficulty="HARD")
    attempted = await insert_problem(app, "attempted-one", difficulty="MEDIUM")
    for pid in (easy1, easy2, hard):
        await set_progress(app, "ada", pid, "SOLVED")
    await set_progress(app, "ada", attempted, "ATTEMPTED")

    async with make_client(app) as client:
        body = (await client.get("/api/users/ada/stats")).json()
    assert body["solved"] == {"easy": 2, "medium": 0, "hard": 1, "total": 3}


async def test_stats_compute_submission_totals_and_acceptance_rate(app):
    await create_user(app, email="bob@example.com", username="bob")
    uid = await user_id(app, "bob")
    problem = await insert_problem(app, "two-sum")
    await add_submission(app, uid, problem, Verdict.ACCEPTED.value)
    await add_submission(app, uid, problem, Verdict.WRONG_ANSWER.value)
    await add_submission(app, uid, problem, Verdict.WRONG_ANSWER.value)
    await add_submission(app, uid, problem, Verdict.WRONG_ANSWER.value)

    async with make_client(app) as client:
        body = (await client.get("/api/users/bob/stats")).json()
    assert (body["total_submissions"], body["accepted_submissions"], body["acceptance_rate"]) == (4, 1, 25.0)


async def test_stats_show_the_current_streak(app):
    await create_user(app, email="cara@example.com", username="cara")
    uid = await user_id(app, "cara")
    async with app.state.sessionmaker() as db:
        db.add(UserStreak(user_id=uid, current_streak=5, longest_streak=12, last_active_date=utcnow().date()))
        await db.commit()

    async with make_client(app) as client:
        body = (await client.get("/api/users/cara/stats")).json()
    assert body["streak"] == {"current": 5, "longest": 12, "last_active_date": utcnow().date().isoformat()}


async def test_stats_list_achievements_earned_and_locked(app):
    await create_user(app, email="dee@example.com", username="dee")
    uid = await user_id(app, "dee")
    key = CATALOG[0].key
    async with app.state.sessionmaker() as db:
        db.add(UserAchievement(user_id=uid, achievement_key=key))
        await db.commit()

    async with make_client(app) as client:
        body = (await client.get("/api/users/dee/stats")).json()
    by_key = {a["key"]: a for a in body["achievements"]}
    assert by_key[key]["earned"] is True
    assert by_key[key]["earned_at"] is not None
    assert by_key[key]["name"] == CATALOG[0].name
    others = [a for a in body["achievements"] if a["key"] != key]
    assert others  # more than one achievement exists
    assert all(a["earned"] is False and a["earned_at"] is None for a in others)
    # Ordered the same way the catalogue is (sort_order, key) — checked via the first entry.
    assert body["achievements"][0]["key"] == CATALOG[0].key


async def test_activity_calendar_is_sparse_and_excludes_old_or_other_users_submissions(app):
    await create_user(app, email="eve@example.com", username="eve")
    await create_user(app, email="mallory@example.com", username="mallory")
    eve_id, mallory_id = await user_id(app, "eve"), await user_id(app, "mallory")
    problem = await insert_problem(app, "two-sum")
    today = utcnow()
    await add_submission(app, eve_id, problem, Verdict.ACCEPTED.value, when=today)
    await add_submission(app, eve_id, problem, Verdict.WRONG_ANSWER.value, when=today)  # same day: one bucket
    await add_submission(app, eve_id, problem, Verdict.ACCEPTED.value, when=today - timedelta(days=2))
    await add_submission(app, eve_id, problem, Verdict.ACCEPTED.value, when=today - timedelta(days=400))  # too old
    await add_submission(app, mallory_id, problem, Verdict.ACCEPTED.value, when=today)  # someone else's activity

    async with make_client(app) as client:
        body = (await client.get("/api/users/eve/stats")).json()
    by_date = {day["date"]: day["count"] for day in body["activity"]}
    assert by_date == {today.date().isoformat(): 2, (today - timedelta(days=2)).date().isoformat(): 1}
    assert (today - timedelta(days=400)).date().isoformat() not in by_date


async def test_achievements_table_has_exactly_the_catalogue_seeded_for_tests(app):
    async with app.state.sessionmaker() as db:
        rows = (await db.scalars(select(Achievement).order_by(Achievement.sort_order))).all()
    assert [r.key for r in rows] == [a.key for a in CATALOG]
    assert all(r.icon and r.name and r.description for r in rows)
