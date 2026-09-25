"""Admin API. Every route is gated server-side by `require_role`; hiding the UI is not access control."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import DbSession
from app.core.pagination import Page, PageParamsDep
from app.modules.admin.analytics import router as analytics_admin_router
from app.modules.admin.contests import router as contests_admin_router
from app.modules.admin.problems import router as problems_admin_router
from app.modules.auth.deps import require_role
from app.modules.users import service as users
from app.modules.users.models import RoleName
from app.modules.users.schemas import AdminUser, to_admin_user

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(RoleName.ADMIN))])


@router.get("/users", response_model=Page[AdminUser])
async def list_users(
    db: DbSession,
    params: PageParamsDep,
    q: Annotated[str | None, Query(max_length=100, description="Match username or email")] = None,
) -> Page[AdminUser]:
    rows, total = await users.list_users(db, params, q)
    return Page.build([to_admin_user(u) for u in rows], total, params)


router.include_router(problems_admin_router)
router.include_router(contests_admin_router)
router.include_router(analytics_admin_router)
