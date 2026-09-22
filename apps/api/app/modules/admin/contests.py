"""Admin contest management. Included by the ADMIN-guarded admin router, so every route requires the ADMIN role."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.deps import DbSession
from app.modules.auth.deps import CurrentUser
from app.modules.contests import service as svc
from app.modules.contests.schemas import ContestAdminInput, ContestAdminOut

router = APIRouter(tags=["admin: contests"])


@router.get("/contests", response_model=list[ContestAdminOut])
async def list_contests(db: DbSession) -> list[ContestAdminOut]:
    return await svc.list_for_admin(db)


@router.post("/contests", response_model=ContestAdminOut, status_code=status.HTTP_201_CREATED)
async def create_contest(body: ContestAdminInput, admin: CurrentUser, db: DbSession) -> ContestAdminOut:
    return await svc.create_contest(db, admin, body)


@router.get("/contests/{contest_id}", response_model=ContestAdminOut)
async def get_contest(contest_id: uuid.UUID, db: DbSession) -> ContestAdminOut:
    return await svc.get_for_admin(db, contest_id)


@router.put("/contests/{contest_id}", response_model=ContestAdminOut)
async def update_contest(contest_id: uuid.UUID, body: ContestAdminInput, db: DbSession) -> ContestAdminOut:
    return await svc.update_contest(db, contest_id, body)


@router.post("/contests/{contest_id}/publish", response_model=ContestAdminOut)
async def publish(contest_id: uuid.UUID, db: DbSession) -> ContestAdminOut:
    return await svc.set_published(db, contest_id, True)


@router.post("/contests/{contest_id}/unpublish", response_model=ContestAdminOut)
async def unpublish(contest_id: uuid.UUID, db: DbSession) -> ContestAdminOut:
    return await svc.set_published(db, contest_id, False)
