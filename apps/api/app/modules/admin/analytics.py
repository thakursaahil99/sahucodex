"""Admin analytics: platform totals plus a read of the `AiUsage` rows that have been recorded since phase 5 but had
nothing reading them until this phase (see the README's phase-5 known limitations). One summary endpoint, not a
dashboard framework — every number here is a plain aggregate query, computed live, never stored or pre-aggregated.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import case, func, select

from app.core.db import utcnow
from app.core.deps import DbSession
from app.modules.ai.models import AiUsage
from app.modules.community.models import Discussion
from app.modules.contests.models import Contest
from app.modules.problems.models import Problem
from app.modules.submissions.models import Submission
from app.modules.users.models import User

router = APIRouter(prefix="/analytics", tags=["admin: analytics"])

_WINDOW_DAYS = 30


class PlatformTotals(BaseModel):
    users: int
    published_problems: int
    submissions: int
    submissions_last_30d: int
    published_contests: int
    discussions: int


class AiFeatureUsage(BaseModel):
    feature: str
    requests: int
    failed: int
    avg_duration_ms: float
    avg_response_chars: float


class AiUsageSummary(BaseModel):
    window_days: int
    total_requests: int
    failed_requests: int
    by_feature: list[AiFeatureUsage]


class AnalyticsOut(BaseModel):
    platform: PlatformTotals
    ai_usage: AiUsageSummary


async def _platform_totals(db: DbSession) -> PlatformTotals:
    since = utcnow() - timedelta(days=_WINDOW_DAYS)
    users = await db.scalar(select(func.count()).select_from(User)) or 0
    published_problems = (
        await db.scalar(
            select(func.count()).select_from(Problem).where(Problem.published.is_(True), Problem.archived_at.is_(None))
        )
    ) or 0
    submissions = await db.scalar(select(func.count()).select_from(Submission)) or 0
    submissions_recent = (
        await db.scalar(select(func.count()).select_from(Submission).where(Submission.created_at >= since))
    ) or 0
    published_contests = (
        await db.scalar(select(func.count()).select_from(Contest).where(Contest.published.is_(True)))
    ) or 0
    discussions = await db.scalar(select(func.count()).select_from(Discussion)) or 0
    return PlatformTotals(
        users=users,
        published_problems=published_problems,
        submissions=submissions,
        submissions_last_30d=submissions_recent,
        published_contests=published_contests,
        discussions=discussions,
    )


async def _ai_usage_summary(db: DbSession) -> AiUsageSummary:
    since = utcnow() - timedelta(days=_WINDOW_DAYS)
    rows = (
        await db.execute(
            select(
                AiUsage.feature,
                func.count().label("requests"),
                func.sum(case((AiUsage.failed.is_(True), 1), else_=0)).label("failed"),
                func.avg(AiUsage.duration_ms).label("avg_duration_ms"),
                func.avg(AiUsage.response_chars).label("avg_response_chars"),
            )
            .where(AiUsage.created_at >= since)
            .group_by(AiUsage.feature)
            .order_by(AiUsage.feature)
        )
    ).all()

    by_feature = [
        AiFeatureUsage(
            feature=row.feature,
            requests=row.requests,
            failed=row.failed or 0,
            avg_duration_ms=round(row.avg_duration_ms or 0.0, 1),
            avg_response_chars=round(row.avg_response_chars or 0.0, 1),
        )
        for row in rows
    ]
    return AiUsageSummary(
        window_days=_WINDOW_DAYS,
        total_requests=sum(f.requests for f in by_feature),
        failed_requests=sum(f.failed for f in by_feature),
        by_feature=by_feature,
    )


@router.get("", response_model=AnalyticsOut)
async def get_analytics(db: DbSession) -> AnalyticsOut:
    return AnalyticsOut(platform=await _platform_totals(db), ai_usage=await _ai_usage_summary(db))
