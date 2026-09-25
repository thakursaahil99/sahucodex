"""Public contest API: browse, register, read a contest's own problems, submit, see standings.

Admin authoring lives in `app.modules.admin.contests` (mounted under the ADMIN-guarded `/admin` router), the same
split as problems.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.core.deps import CacheDep, DbSession, RedisDep, SettingsDep
from app.core.queue import JobQueue
from app.core.rate_limit import get_rate_limiter
from app.modules.auth.deps import CurrentUser, OptionalUser
from app.modules.contests import service as svc
from app.modules.contests.schemas import (
    ContestDetail,
    ContestListItem,
    ContestProblemOut,
    ContestRunCreate,
    ContestSubmitCreate,
    StandingsOut,
)
from app.modules.submissions.models import SubmissionStatus
from app.modules.submissions.schemas import RunQueued, SubmissionQueued
from app.modules.submissions.service import create_and_enqueue, run_for, validate_source

router = APIRouter(prefix="/contests", tags=["contests"])


def _queue(request: Request) -> JobQueue:
    return request.app.state.queue


@router.get("", response_model=list[ContestListItem])
async def list_contests(db: DbSession) -> list[ContestListItem]:
    return await svc.list_contests(db)


@router.get("/{slug}", response_model=ContestDetail)
async def get_contest(slug: str, db: DbSession, user: OptionalUser) -> ContestDetail:
    return await svc.get_contest_detail(db, slug, user)


@router.post("/{slug}/register", status_code=status.HTTP_204_NO_CONTENT)
async def register(slug: str, db: DbSession, user: CurrentUser) -> None:
    await svc.register(db, slug, user)


@router.get("/{slug}/problems/{label}", response_model=ContestProblemOut)
async def get_contest_problem(slug: str, label: str, db: DbSession) -> ContestProblemOut:
    return await svc.get_contest_problem(db, slug, label)


@router.post("/{slug}/problems/{label}/submit", response_model=SubmissionQueued, status_code=status.HTTP_202_ACCEPTED)
async def submit_contest_problem(
    slug: str,
    label: str,
    data: ContestSubmitCreate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> SubmissionQueued:
    # Shares the plain submit path's rate-limit budget: a contest submission is exactly as expensive to judge.
    await get_rate_limiter(request).enforce("submit", str(user.id), settings.rate_limit_submit)
    contest, problem, language_key = await svc.resolve_contest_submission(db, slug, label, user, data.language)
    validate_source(settings, data.source_code)
    submission = await create_and_enqueue(
        db, redis, _queue(request), settings, user, problem, language_key, data.source_code, contest_id=contest.id
    )
    return SubmissionQueued(id=submission.id, status=SubmissionStatus(submission.status))


@router.post("/{slug}/problems/{label}/run", response_model=RunQueued, status_code=status.HTTP_202_ACCEPTED)
async def run_contest_problem(
    slug: str,
    label: str,
    data: ContestRunCreate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    redis: RedisDep,
    settings: SettingsDep,
) -> RunQueued:
    await get_rate_limiter(request).enforce("run", str(user.id), settings.rate_limit_run)
    _contest, problem, language_key = await svc.resolve_contest_submission(db, slug, label, user, data.language)
    run_id = await run_for(
        db, redis, _queue(request), settings, user, problem, language_key, data.source_code, data.mode, data.input
    )
    return RunQueued(id=run_id)


@router.get("/{slug}/standings", response_model=StandingsOut)
async def get_standings(slug: str, db: DbSession, cache: CacheDep) -> StandingsOut:
    contest = await svc.get_contest(db, slug)
    return await svc.compute_standings(db, contest, cache)
