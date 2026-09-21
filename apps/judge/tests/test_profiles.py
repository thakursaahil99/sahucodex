"""Streaks and achievements (app/modules/profiles), tested directly against a database session — faster and more
precise than driving them through a full judged submission for every scenario. test_pipeline.py separately proves
the wiring: an ACCEPTED submission really does call these and really does publish an event, in the right order.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from dbsupport import World, new_world
from sqlalchemy import select
from support import ScriptedSandbox, exited

from app.core.db import utcnow
from app.modules.problems.models import Difficulty, Problem, ProblemTag, ProgressStatus, Tag, UserProblemProgress
from app.modules.profiles import achievements
from app.modules.profiles.models import UserAchievement, UserStreak
from app.modules.profiles.service import evaluate_achievements, get_profile_stats, record_streak
from app.modules.submissions.models import Submission, SubmissionStatus, Verdict
from app.modules.users.models import User


@pytest.fixture
async def world():
    w = await new_world(ScriptedSandbox(lambda _: exited("")))
    yield w
    await w.close()


async def get_streak(world: World, user_id: uuid.UUID) -> UserStreak | None:
    async with world.sessionmaker() as db:
        return await db.get(UserStreak, user_id)


async def set_last_active(world: World, user_id: uuid.UUID, days_ago: int) -> None:
    async with world.sessionmaker() as db:
        row = await db.get(UserStreak, user_id)
        row.last_active_date = utcnow().date() - timedelta(days=days_ago)
        await db.commit()


# --- streaks --------------------------------------------------------------------------------------------------------


async def test_the_first_accepted_submission_starts_a_streak_of_one(world: World) -> None:
    user = await world.add_user()
    async with world.sessionmaker() as db:
        await record_streak(db, user)
        await db.commit()
    streak = await get_streak(world, user)
    assert (streak.current_streak, streak.longest_streak, streak.last_active_date) == (1, 1, utcnow().date())


async def test_a_second_accepted_submission_the_same_day_does_not_double_count(world: World) -> None:
    user = await world.add_user()
    async with world.sessionmaker() as db:
        await record_streak(db, user)
        await record_streak(db, user)
        await db.commit()
    streak = await get_streak(world, user)
    assert (streak.current_streak, streak.longest_streak) == (1, 1)


async def test_an_accepted_submission_the_next_day_extends_the_streak(world: World) -> None:
    user = await world.add_user()
    async with world.sessionmaker() as db:
        await record_streak(db, user)
        await db.commit()
    await set_last_active(world, user, days_ago=1)
    async with world.sessionmaker() as db:
        await record_streak(db, user)
        await db.commit()
    streak = await get_streak(world, user)
    assert (streak.current_streak, streak.longest_streak, streak.last_active_date) == (2, 2, utcnow().date())


async def test_a_gap_resets_the_current_streak_but_keeps_the_longest(world: World) -> None:
    user = await world.add_user()
    async with world.sessionmaker() as db:
        await record_streak(db, user)
        await db.commit()
    await set_last_active(world, user, days_ago=1)
    async with world.sessionmaker() as db:
        await record_streak(db, user)  # current=2, longest=2
        await db.commit()
    await set_last_active(world, user, days_ago=5)  # missed several days
    async with world.sessionmaker() as db:
        await record_streak(db, user)
        await db.commit()
    streak = await get_streak(world, user)
    assert (streak.current_streak, streak.longest_streak) == (1, 2)


async def test_streaks_are_independent_per_user(world: World) -> None:
    ada, bob = await world.add_user("ada"), await world.add_user("bob")
    async with world.sessionmaker() as db:
        await record_streak(db, ada)
        await db.commit()
    assert (await get_streak(world, ada)).current_streak == 1
    assert await get_streak(world, bob) is None


# --- achievements: individual checks ----------------------------------------------------------------------------------


async def solve(world: World, user: uuid.UUID, difficulty: str = "EASY", tags: tuple[str, ...] = ()) -> None:
    """Marks a fresh problem SOLVED for `user`, optionally tagged, without going through the judge."""
    async with world.sessionmaker() as db:
        problem = Problem(
            id=uuid.uuid4(),
            slug=f"p-{uuid.uuid4().hex[:8]}",
            title="x",
            description="d" * 10,
            difficulty=difficulty,
            constraints="c",
            input_format="i",
            output_format="o",
            published=True,
        )
        db.add(problem)
        await db.flush()
        for name in tags:
            tag = await db.scalar(select(Tag).where(Tag.name == name))
            if tag is None:
                tag = Tag(id=uuid.uuid4(), name=name, slug=name.lower())
                db.add(tag)
                await db.flush()
            db.add(ProblemTag(problem_id=problem.id, tag_id=tag.id))
        db.add(UserProblemProgress(user_id=user, problem_id=problem.id, status=ProgressStatus.SOLVED.value, attempts=1))
        await db.commit()


async def add_accepted_submission(world: World, user: uuid.UUID, *, language: str = "python") -> None:
    async with world.sessionmaker() as db:
        db.add(
            Submission(
                user_id=user,
                problem_id=(await world.add_problem(f"s-{uuid.uuid4().hex[:8]}")),
                language_key=language,
                source_code="x",
                status=SubmissionStatus.COMPLETED.value,
                verdict=Verdict.ACCEPTED.value,
                total_count=1,
                passed_count=1,
            )
        )
        await db.commit()


@pytest.mark.parametrize(
    ("key", "unmet", "met"),
    [
        ("first_solve", 0, 1),
        ("ten_solved", 9, 10),
    ],
)
async def test_solved_count_thresholds(world: World, key: str, unmet: int, met: int) -> None:
    user = await world.add_user()
    for _ in range(unmet):
        await solve(world, user)
    async with world.sessionmaker() as db:
        assert await achievements.CHECKS[key](db, user) is False
    await solve(world, user)  # unmet + 1 == met
    async with world.sessionmaker() as db:
        assert await achievements.CHECKS[key](db, user) is True


async def test_all_difficulties_needs_one_of_each(world: World) -> None:
    user = await world.add_user()
    async with world.sessionmaker() as db:
        check = achievements.CHECKS["all_difficulties"]
        assert await check(db, user) is False
    await solve(world, user, difficulty=Difficulty.EASY.value)
    await solve(world, user, difficulty=Difficulty.MEDIUM.value)
    async with world.sessionmaker() as db:
        assert await check(db, user) is False
    await solve(world, user, difficulty=Difficulty.HARD.value)
    async with world.sessionmaker() as db:
        assert await check(db, user) is True


async def test_polyglot_needs_accepted_submissions_in_two_languages(world: World) -> None:
    user = await world.add_user()
    check = achievements.CHECKS["polyglot"]
    await add_accepted_submission(world, user, language="python")
    async with world.sessionmaker() as db:
        assert await check(db, user) is False
    await add_accepted_submission(world, user, language="cpp")
    async with world.sessionmaker() as db:
        assert await check(db, user) is True


async def test_topic_explorer_needs_ten_distinct_solved_topics(world: World) -> None:
    user = await world.add_user()
    check = achievements.CHECKS["topic_explorer"]
    for i in range(9):
        await solve(world, user, tags=(f"topic-{i}",))
    async with world.sessionmaker() as db:
        assert await check(db, user) is False
    await solve(world, user, tags=("topic-9",))
    async with world.sessionmaker() as db:
        assert await check(db, user) is True


async def test_topic_explorer_does_not_count_the_same_topic_twice(world: World) -> None:
    user = await world.add_user()
    check = achievements.CHECKS["topic_explorer"]
    for _ in range(10):
        await solve(world, user, tags=("same-topic",))
    async with world.sessionmaker() as db:
        assert await check(db, user) is False


@pytest.mark.parametrize(("key", "threshold"), [("streak_7", 7), ("streak_30", 30)])
async def test_streak_thresholds_use_the_longest_ever_reached(world: World, key: str, threshold: int) -> None:
    user = await world.add_user()
    async with world.sessionmaker() as db:
        db.add(
            UserStreak(user_id=user, current_streak=1, longest_streak=threshold - 1, last_active_date=utcnow().date())
        )
        await db.commit()
        assert await achievements.CHECKS[key](db, user) is False
    async with world.sessionmaker() as db:
        (await db.get(UserStreak, user)).longest_streak = threshold
        await db.commit()
        assert await achievements.CHECKS[key](db, user) is True


async def test_hundred_submissions_counts_every_verdict(world: World) -> None:
    user = await world.add_user()
    check = achievements.CHECKS["hundred_submissions"]
    for _ in range(99):
        await add_accepted_submission(world, user)
    async with world.sessionmaker() as db:
        assert await check(db, user) is False
    await add_accepted_submission(world, user)
    async with world.sessionmaker() as db:
        assert await check(db, user) is True


# --- evaluate_achievements: orchestration ------------------------------------------------------------------------------


async def test_evaluate_achievements_grants_exactly_the_newly_met_ones(world: World) -> None:
    user = await world.add_user()
    await solve(world, user)
    async with world.sessionmaker() as db:
        newly = await evaluate_achievements(db, user)
        await db.commit()
    assert newly == ["first_solve"]
    async with world.sessionmaker() as db:
        earned = (
            await db.scalars(select(UserAchievement.achievement_key).where(UserAchievement.user_id == user))
        ).all()
    assert earned == ["first_solve"]


async def test_evaluate_achievements_never_re_grants_the_same_key(world: World) -> None:
    user = await world.add_user()
    await solve(world, user)
    async with world.sessionmaker() as db:
        await evaluate_achievements(db, user)
        await db.commit()
    for _ in range(9):
        await solve(world, user)
    async with world.sessionmaker() as db:
        newly = await evaluate_achievements(db, user)
        await db.commit()
    assert newly == ["ten_solved"]  # first_solve is not granted again
    async with world.sessionmaker() as db:
        rows = (await db.scalars(select(UserAchievement).where(UserAchievement.user_id == user))).all()
    assert sorted(r.achievement_key for r in rows) == ["first_solve", "ten_solved"]


async def test_evaluate_achievements_grants_nothing_for_a_fresh_user(world: World) -> None:
    user = await world.add_user()
    async with world.sessionmaker() as db:
        assert await evaluate_achievements(db, user) == []


# --- get_profile_stats ---------------------------------------------------------------------------------------------


async def test_profile_stats_combine_solved_counts_streak_and_achievements(world: World) -> None:
    user = await world.add_user()
    await solve(world, user, difficulty="EASY")
    await solve(world, user, difficulty="EASY")
    await solve(world, user, difficulty="HARD")
    await add_accepted_submission(world, user)
    async with world.sessionmaker() as db:
        await record_streak(db, user)
        await evaluate_achievements(db, user)
        await db.commit()

    async with world.sessionmaker() as db:
        row = await db.get(User, user)
        stats = await get_profile_stats(db, row)

    assert (stats.solved.easy, stats.solved.hard, stats.solved.total) == (2, 1, 3)
    assert stats.total_submissions == 1
    assert stats.accepted_submissions == 1
    assert stats.acceptance_rate == 100.0
    assert (stats.streak.current, stats.streak.longest) == (1, 1)
    earned_keys = {a.key for a in stats.achievements if a.earned}
    assert "first_solve" in earned_keys
    locked = [a for a in stats.achievements if not a.earned]
    assert all(a.earned_at is None for a in locked)
    assert len(stats.achievements) == len(achievements.CATALOG)


async def test_profile_stats_for_a_fresh_user_show_zeros_and_no_locked_out_achievements_hidden(world: World) -> None:
    user = await world.add_user()
    async with world.sessionmaker() as db:
        row = await db.get(User, user)
        stats = await get_profile_stats(db, row)
    assert (stats.solved.total, stats.total_submissions, stats.acceptance_rate) == (0, 0, None)
    assert (stats.streak.current, stats.streak.longest, stats.streak.last_active_date) == (0, 0, None)
    assert stats.activity == []
    assert len(stats.achievements) == len(achievements.CATALOG)
    assert all(not a.earned for a in stats.achievements)
