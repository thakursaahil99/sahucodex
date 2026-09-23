"""Moderation: the reports queue and resolving a report. Gated by MODERATOR (ADMIN also qualifies, since
`require_role` is a minimum-rank check) rather than the plain admin router's ADMIN-only gate — moderation is
deliberately a lower bar than full admin access (problem authoring, user management, contest creation)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import DbSession
from app.modules.auth.deps import CurrentUser, require_role
from app.modules.community import service as svc
from app.modules.community.schemas import ReportOut, ReportResolve
from app.modules.users.models import RoleName

router = APIRouter(
    prefix="/moderation", tags=["moderation"], dependencies=[Depends(require_role(RoleName.MODERATOR))]
)


@router.get("/reports", response_model=list[ReportOut])
async def list_reports(db: DbSession, status_filter: str | None = Query(None, alias="status")) -> list[ReportOut]:
    return await svc.list_reports(db, status_filter)


@router.post("/reports/{report_id}/resolve", status_code=status.HTTP_204_NO_CONTENT)
async def resolve_report(report_id: uuid.UUID, body: ReportResolve, moderator: CurrentUser, db: DbSession) -> None:
    await svc.resolve_report(db, report_id, moderator, body.action)
