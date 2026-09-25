"""Public problem API. Every response is built from `ProblemPublic`-style schemas that cannot carry hidden tests."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.core.deps import CacheDep, DbSession
from app.core.errors import not_found, unauthorized
from app.core.pagination import Page, PageParamsDep
from app.modules.auth.deps import CurrentUser, OptionalUser
from app.modules.problems import service
from app.modules.problems.models import Difficulty, Problem
from app.modules.problems.schemas import (
    HintOut,
    LanguageOut,
    ProblemDetail,
    ProblemListItem,
    TagWithCount,
)
from app.modules.users.models import RoleName, User

router = APIRouter(tags=["problems"])


@router.get("/problems", response_model=Page[ProblemListItem])
async def list_problems(
    db: DbSession,
    params: PageParamsDep,
    user: OptionalUser,
    q: Annotated[str | None, Query(max_length=100, description="Search title, description and tags")] = None,
    difficulty: Annotated[list[Difficulty] | None, Query(description="Repeat for several")] = None,
    tag: Annotated[list[str] | None, Query(max_length=10, description="Tag slug; matches ANY of those given")] = None,
    status: Annotated[Literal["solved", "unsolved", "attempted"] | None, Query(description="Needs sign-in")] = None,
    min_acceptance: Annotated[float | None, Query(ge=0, le=100)] = None,
    max_acceptance: Annotated[float | None, Query(ge=0, le=100)] = None,
    sort: Literal["newest", "title", "difficulty", "acceptance", "relevance"] = "newest",
) -> Page[ProblemListItem]:
    if status is not None and user is None:
        raise unauthorized("NOT_AUTHENTICATED", "Sign in to filter by your progress")
    filters = service.ProblemFilters(
        q=(q or "").strip() or None,
        difficulties=[d.value for d in difficulty or []],
        tags=tag or [],
        status=status,
        min_acceptance=min_acceptance,
        max_acceptance=max_acceptance,
        sort=sort,
    )
    items, total = await service.list_problems(db, params, filters, user)
    return Page.build(items, total, params)


@router.get("/problems/{slug}", response_model=ProblemDetail)
async def get_problem(slug: str, db: DbSession, cache: CacheDep, user: OptionalUser) -> ProblemDetail:
    public = await service.get_public_problem(db, cache, slug)
    if public is None:
        raise not_found("PROBLEM_NOT_FOUND", "Problem not found")

    status = await service.progress_status(db, user, public.id)
    detail = ProblemDetail(**public.model_dump(), status=status)
    if _may_see_solution(user, status):
        # The editorial is deliberately not part of the cached payload: it is only loaded for viewers entitled to it.
        problem = await service.find_visible_problem(db, slug)
        if problem is not None:
            detail.solution_unlocked = True
            detail.editorial = problem.editorial
            detail.expected_time_complexity = problem.expected_time_complexity
            detail.expected_space_complexity = problem.expected_space_complexity
    return detail


def _may_see_solution(user: User | None, status: str | None) -> bool:
    if user is None:
        return False
    return status == "SOLVED" or user.has_role(RoleName.ADMIN)


@router.get("/problems/{slug}/hints/{index}", response_model=HintOut)
async def get_hint(slug: str, index: int, db: DbSession) -> HintOut:
    """Hints are revealed one at a time instead of being sent with the statement. `index` is 1-based."""
    problem: Problem | None = await service.find_visible_problem(db, slug)
    if problem is None:
        raise not_found("PROBLEM_NOT_FOUND", "Problem not found")
    hints = list(problem.hints or [])
    if not 1 <= index <= len(hints):
        raise not_found("HINT_NOT_FOUND", "That hint does not exist")
    return HintOut(index=index, total=len(hints), hint=hints[index - 1])


@router.get("/recommendations", response_model=list[ProblemListItem])
async def get_recommendations(db: DbSession, user: CurrentUser) -> list[ProblemListItem]:
    """Personalised "what to solve next", from the caller's own solved-tag history and difficulty progression —
    see `service.recommend_problems` for the ranking. Signed-in only: there is no meaningful recommendation for an
    anonymous caller with no history."""
    return await service.recommend_problems(db, user)


@router.get("/tags", response_model=list[TagWithCount])
async def list_tags(db: DbSession, cache: CacheDep) -> list[TagWithCount]:
    return await service.list_tags(db, cache)


@router.get("/languages", response_model=list[LanguageOut])
async def list_languages(db: DbSession, cache: CacheDep) -> list[LanguageOut]:
    return await service.list_languages(db, cache)
