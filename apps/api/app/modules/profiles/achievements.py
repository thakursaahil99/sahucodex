"""The achievement catalogue: one small, pure `check(db, user_id) -> bool` per achievement, plus the display text for
each — name, description, icon.

Every key in `CHECKS` must have a matching entry in `CATALOG`, and a matching row in the `achievements` table seeded
by migration 0004 — a test guards both. `CATALOG` exists so tests have one place to seed the real catalogue instead
of inventing their own (the migration keeps its own independent, frozen copy of the same rows: a migration must
never import application code whose content could change later and silently rewrite history — see migration 0002's
language seed for the same reasoning). Checks run for achievements a user has not already earned yet, after every
judged submission (see `service.evaluate_achievements`).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.problems.models import Problem, ProblemTag, ProgressStatus, UserProblemProgress
from app.modules.profiles.models import UserStreak
from app.modules.submissions.models import Submission, Verdict

Check = Callable[[AsyncSession, uuid.UUID], Awaitable[bool]]


@dataclass(frozen=True)
class AchievementDef:
    key: str
    name: str
    description: str
    icon: str  # a lucide-react icon name, rendered client-side only
    sort_order: int


REQUIRED_DIFFICULTIES = frozenset({"EASY", "MEDIUM", "HARD"})


async def _solved_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(UserProblemProgress)
            .where(UserProblemProgress.user_id == user_id, UserProblemProgress.status == ProgressStatus.SOLVED.value)
        )
        or 0
    )


async def check_first_solve(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return await _solved_count(db, user_id) >= 1


async def check_ten_solved(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return await _solved_count(db, user_id) >= 10


async def check_all_difficulties(db: AsyncSession, user_id: uuid.UUID) -> bool:
    rows = await db.scalars(
        select(Problem.difficulty)
        .join(UserProblemProgress, UserProblemProgress.problem_id == Problem.id)
        .where(UserProblemProgress.user_id == user_id, UserProblemProgress.status == ProgressStatus.SOLVED.value)
        .distinct()
    )
    return REQUIRED_DIFFICULTIES.issubset(rows.all())


async def check_polyglot(db: AsyncSession, user_id: uuid.UUID) -> bool:
    count = await db.scalar(
        select(func.count(func.distinct(Submission.language_key))).where(
            Submission.user_id == user_id, Submission.verdict == Verdict.ACCEPTED.value
        )
    )
    return (count or 0) >= 2


async def check_topic_explorer(db: AsyncSession, user_id: uuid.UUID) -> bool:
    count = await db.scalar(
        select(func.count(func.distinct(ProblemTag.tag_id)))
        .select_from(UserProblemProgress)
        .join(ProblemTag, ProblemTag.problem_id == UserProblemProgress.problem_id)
        .where(UserProblemProgress.user_id == user_id, UserProblemProgress.status == ProgressStatus.SOLVED.value)
    )
    return (count or 0) >= 10


async def _longest_streak(db: AsyncSession, user_id: uuid.UUID) -> int:
    return await db.scalar(select(UserStreak.longest_streak).where(UserStreak.user_id == user_id)) or 0


async def check_streak_7(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return await _longest_streak(db, user_id) >= 7


async def check_streak_30(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return await _longest_streak(db, user_id) >= 30


async def check_hundred_submissions(db: AsyncSession, user_id: uuid.UUID) -> bool:
    count = await db.scalar(select(func.count()).select_from(Submission).where(Submission.user_id == user_id))
    return (count or 0) >= 100


CHECKS: dict[str, Check] = {
    "first_solve": check_first_solve,
    "ten_solved": check_ten_solved,
    "all_difficulties": check_all_difficulties,
    "polyglot": check_polyglot,
    "topic_explorer": check_topic_explorer,
    "streak_7": check_streak_7,
    "streak_30": check_streak_30,
    "hundred_submissions": check_hundred_submissions,
}

# Must match database/migrations/versions/0004_profiles.py's ACHIEVEMENTS exactly (name/description/icon/order) — a
# test in test_seed_catalog.py-style guards it. Kept here, not imported from the migration, for the reason above.
CATALOG: tuple[AchievementDef, ...] = (
    AchievementDef("first_solve", "First Blood", "Solve your first problem.", "Sparkles", 1),
    AchievementDef("ten_solved", "Problem Solver", "Solve 10 problems.", "Trophy", 2),
    AchievementDef(
        "all_difficulties",
        "Well Rounded",
        "Solve at least one Easy, one Medium and one Hard problem.",
        "Layers",
        3,
    ),
    AchievementDef("polyglot", "Polyglot", "Get an accepted submission in two different languages.", "Languages", 4),
    AchievementDef("topic_explorer", "Topic Explorer", "Solve problems across 10 different topics.", "Compass", 5),
    AchievementDef("streak_7", "One Week Streak", "Reach a 7-day solving streak.", "Flame", 6),
    AchievementDef("streak_30", "One Month Streak", "Reach a 30-day solving streak.", "CalendarCheck", 7),
    AchievementDef("hundred_submissions", "Persistent", "Make 100 submissions.", "Target", 8),
)
