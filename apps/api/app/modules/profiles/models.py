"""Streaks and achievements: what phase 4 adds on top of a user's account and problem progress.

Everything here is derived from activity that already exists elsewhere (`submissions`, `user_problem_progress`) plus
these three small tables. Nothing is admin-authored or user-editable; SahuJudge writes it after judging."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime, utcnow


class UserStreak(Base):
    """One row per user, created on their first ACCEPTED submission. `last_active_date` is a UTC calendar date —
    dates, not timestamps, so "was yesterday active" is a plain equality check, not a timezone-sensitive range."""

    __tablename__ = "user_streaks"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    current_streak: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    longest_streak: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    last_active_date: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, server_default=func.now()
    )


class Achievement(Base):
    """Reference table, seeded by the migration (like `tags`/`programming_languages`). Criteria are evaluated in
    code (`app/modules/profiles/achievements.py`), not stored here — this table only holds what the UI needs to
    render one, earned or not: a name, a description a learner can read as a goal, and an icon."""

    __tablename__ = "achievements"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    icon: Mapped[str] = mapped_column(String(40))  # a lucide-react icon name, rendered client-side only
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


class UserAchievement(Base):
    __tablename__ = "user_achievements"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    achievement_key: Mapped[str] = mapped_column(ForeignKey("achievements.key", ondelete="CASCADE"), primary_key=True)
    earned_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, server_default=func.now())
