"""Admin problem management. Included by the ADMIN-guarded admin router, so every route requires the ADMIN role."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, status

from app.core.deps import CacheDep, DbSession, EmbeddingProviderDep, QdrantDep, SettingsDep
from app.core.net import client_ip, user_agent
from app.core.pagination import Page, PageParamsDep
from app.modules.auth.deps import CurrentUser
from app.modules.problems import admin_service as svc
from app.modules.problems.schemas import (
    AdminProblemListItem,
    ProblemAdminOut,
    ProblemInput,
    TagCreate,
    TagOut,
    ValidationReport,
)
from app.modules.rag import service as rag

router = APIRouter(tags=["admin: problems"])


@router.get("/problems", response_model=Page[AdminProblemListItem])
async def list_problems(
    db: DbSession,
    params: PageParamsDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[Literal["DRAFT", "PUBLISHED", "ARCHIVED"] | None, Query(alias="status")] = None,
) -> Page[AdminProblemListItem]:
    items, total = await svc.list_for_admin(db, params, q, status_filter)
    return Page.build(items, total, params)


@router.post("/problems", response_model=ProblemAdminOut, status_code=status.HTTP_201_CREATED)
async def create_problem(
    body: ProblemInput,
    request: Request,
    admin: CurrentUser,
    db: DbSession,
    cache: CacheDep,
    qdrant: QdrantDep,
    embedder: EmbeddingProviderDep,
    settings: SettingsDep,
) -> ProblemAdminOut:
    problem = await svc.create_problem(db, cache, admin, body, ip=client_ip(request), user_agent=user_agent(request))
    await rag.index_problem(qdrant, embedder, settings, problem)
    return svc.to_admin_out(problem)


@router.get("/problems/{problem_id}", response_model=ProblemAdminOut)
async def get_problem(problem_id: uuid.UUID, db: DbSession) -> ProblemAdminOut:
    return svc.to_admin_out(await svc.load_problem(db, problem_id))


@router.put("/problems/{problem_id}", response_model=ProblemAdminOut)
async def update_problem(
    problem_id: uuid.UUID,
    body: ProblemInput,
    request: Request,
    admin: CurrentUser,
    db: DbSession,
    cache: CacheDep,
    qdrant: QdrantDep,
    embedder: EmbeddingProviderDep,
    settings: SettingsDep,
) -> ProblemAdminOut:
    problem = await svc.update_problem(
        db, cache, admin, problem_id, body, ip=client_ip(request), user_agent=user_agent(request)
    )
    await rag.index_problem(qdrant, embedder, settings, problem)
    return svc.to_admin_out(problem)


@router.get("/problems/{problem_id}/validation", response_model=ValidationReport)
async def validate(problem_id: uuid.UUID, db: DbSession) -> ValidationReport:
    """Dry run of the checks `publish` enforces, so the editor can show what is still missing."""
    problem = await svc.load_problem(db, problem_id)
    issues = svc.validate_problem(problem, await svc.enabled_language_keys(db))
    return ValidationReport(ok=not issues, issues=issues)


def _state_route(action: svc.Action):
    async def handler(
        problem_id: uuid.UUID,
        request: Request,
        admin: CurrentUser,
        db: DbSession,
        cache: CacheDep,
        qdrant: QdrantDep,
        embedder: EmbeddingProviderDep,
        settings: SettingsDep,
    ) -> ProblemAdminOut:
        problem = await svc.change_state(
            db, cache, admin, problem_id, action, ip=client_ip(request), user_agent=user_agent(request)
        )
        # index_problem itself no-ops (removes any existing vector) for a problem that isn't published/is archived,
        # so this one call is correct for publish, unpublish, archive, and restore alike.
        await rag.index_problem(qdrant, embedder, settings, problem)
        return svc.to_admin_out(problem)

    handler.__name__ = f"{action}_problem"
    return handler


for _action in ("publish", "unpublish", "archive", "restore"):
    router.add_api_route(
        f"/problems/{{problem_id}}/{_action}", _state_route(_action), methods=["POST"], response_model=ProblemAdminOut
    )


@router.post("/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(body: TagCreate, db: DbSession, cache: CacheDep) -> TagOut:
    tag = await svc.create_tag(db, cache, body.name)
    return TagOut(name=tag.name, slug=tag.slug)
