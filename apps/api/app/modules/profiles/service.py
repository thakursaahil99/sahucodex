"""Streak/achievement writes (called by SahuJudge after judging) and the stats read (the public profile API).

Nothing here executes user code or touches hidden tests; it only aggregates data other modules already wrote.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.modules.problems.models import Problem, ProgressStatus, UserProblemProgress
from app.modules.profiles import achievements
from app.modules.profiles.models import Achievement, UserAchievement, UserStreak
from app.modules.profiles.schemas import AchievementOut, ActivityDay, DifficultyCounts, ProfileStats, StreakOut
from app.modules.submissions.models import Submission, Verdict
from app.modules.users.models import User

ACTIVITY_WINDOW_DAYS = 365


async def record_streak(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Marks today (UTC) as an active day. Idempotent per day — a second ACCEPTED submission the same day is a
    no-op — and atomic under concurrent judging: an UPDATE with the new value computed in SQL, falling back to an
    INSERT (and, on a race, one more UPDATE) if no row exists yet. Mirrors the pattern in
    sahujudge.pipeline.record_progress. Does not commit; the caller commits once, with everything else."""
    today = utcnow().date()
    yesterday = today - timedelta(days=1)
    new_current = case(
        (UserStreak.last_active_date == today, UserStreak.current_streak),
        (UserStreak.last_active_date == yesterday, UserStreak.current_streak + 1),
        else_=1,
    )
    new_longest = case((new_current > UserStreak.longest_streak, new_current), else_=UserStreak.longest_streak)
    values = {"current_streak": new_current, "longest_streak": new_longest, "last_active_date": today}

    result = await db.execute(update(UserStreak).where(UserStreak.user_id == user_id).values(**values))
    if result.rowcount:  # type: ignore[attr-defined]
        return
    try:
        async with db.begin_nested():
            db.add(UserStreak(user_id=user_id, current_streak=1, longest_streak=1, last_active_date=today))
            await db.flush()
    except IntegrityError:  # another worker created the row between our UPDATE and INSERT
        await db.execute(update(UserStreak).where(UserStreak.user_id == user_id).values(**values))


async def evaluate_achievements(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Checks every achievement the user has not yet earned and stages a row for each newly met one. Runs after
    every judged submission (not just accepted ones), since some achievements — a submission count — can become
    true on a failing attempt too. Returns the keys earned just now. Does not commit."""
    earned_query = select(UserAchievement.achievement_key).where(UserAchievement.user_id == user_id)
    already = set((await db.scalars(earned_query)).all())
    newly: list[str] = []
    for key, check in achievements.CHECKS.items():
        if key in already:
            continue
        if await check(db, user_id):
            db.add(UserAchievement(user_id=user_id, achievement_key=key))
            newly.append(key)
    return newly


def _to_iso_date(value: object) -> str:
    """`func.date(...)` returns a native `date` on PostgreSQL but a string on SQLite; normalise to one ISO shape."""
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


async def get_profile_stats(db: AsyncSession, user: User) -> ProfileStats:
    solved_rows = (
        await db.execute(
            select(Problem.difficulty, func.count())
            .select_from(UserProblemProgress)
            .join(Problem, Problem.id == UserProblemProgress.problem_id)
            .where(UserProblemProgress.user_id == user.id, UserProblemProgress.status == ProgressStatus.SOLVED.value)
            .group_by(Problem.difficulty)
        )
    ).all()
    counts = {difficulty: count for difficulty, count in solved_rows}
    solved = DifficultyCounts(
        easy=counts.get("EASY", 0),
        medium=counts.get("MEDIUM", 0),
        hard=counts.get("HARD", 0),
        total=sum(counts.values()),
    )

    total, accepted = (
        await db.execute(
            select(
                func.count(),
                func.sum(case((Submission.verdict == Verdict.ACCEPTED.value, 1), else_=0)),
            ).where(Submission.user_id == user.id)
        )
    ).one()
    accepted = accepted or 0
    acceptance_rate = round(accepted * 100 / total, 1) if total else None

    streak_row = await db.get(UserStreak, user.id)
    last_active = streak_row.last_active_date if streak_row else None
    streak = StreakOut(
        current=streak_row.current_streak if streak_row else 0,
        longest=streak_row.longest_streak if streak_row else 0,
        last_active_date=last_active.isoformat() if last_active else None,
    )

    earned = {
        row.achievement_key: row.earned_at
        for row in await db.scalars(select(UserAchievement).where(UserAchievement.user_id == user.id))
    }
    catalogue = (await db.scalars(select(Achievement).order_by(Achievement.sort_order, Achievement.key))).all()
    achievement_list = [
        AchievementOut(
            key=a.key,
            name=a.name,
            description=a.description,
            icon=a.icon,
            earned=a.key in earned,
            earned_at=earned.get(a.key),
        )
        for a in catalogue
    ]

    since = utcnow() - timedelta(days=ACTIVITY_WINDOW_DAYS)
    activity_rows = (
        await db.execute(
            select(func.date(Submission.created_at), func.count())
            .where(Submission.user_id == user.id, Submission.created_at >= since)
            .group_by(func.date(Submission.created_at))
        )
    ).all()
    activity = sorted(
        (ActivityDay(date=_to_iso_date(day), count=count) for day, count in activity_rows), key=lambda a: a.date
    )

    return ProfileStats(
        solved=solved,
        total_submissions=total,
        accepted_submissions=accepted,
        acceptance_rate=acceptance_rate,
        streak=streak,
        achievements=achievement_list,
        activity=activity,
    )
