from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DifficultyCounts(BaseModel):
    easy: int
    medium: int
    hard: int
    total: int


class StreakOut(BaseModel):
    current: int
    longest: int
    last_active_date: str | None  # ISO date (YYYY-MM-DD), UTC


class AchievementOut(BaseModel):
    key: str
    name: str
    description: str
    icon: str
    earned: bool
    earned_at: datetime | None


class ActivityDay(BaseModel):
    date: str  # ISO date (YYYY-MM-DD), UTC
    count: int


class ProfileStats(BaseModel):
    """Public: solved counts, streak and achievements are shown the same way GitHub/LeetCode show public activity —
    aggregate numbers and dates, never the submissions or code behind them."""

    solved: DifficultyCounts
    total_submissions: int
    accepted_submissions: int
    acceptance_rate: float | None
    streak: StreakOut
    achievements: list[AchievementOut]
    activity: list[ActivityDay]  # sparse: only days with at least one submission, most recent 365 days
