"""Public profile statistics — solved counts, streak, achievements, activity calendar.

Mounted under /users, alongside app.modules.users.router, so a profile's stats sit next to its public profile at
GET /api/users/{username} and GET /api/users/{username}/stats.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import DbSession
from app.core.errors import not_found
from app.modules.profiles.schemas import ProfileStats
from app.modules.profiles.service import get_profile_stats
from app.modules.users import service as users

router = APIRouter(prefix="/users", tags=["profiles"])


@router.get("/{username}/stats", response_model=ProfileStats)
async def get_stats(username: str, db: DbSession) -> ProfileStats:
    user = await users.get_by_username(db, username)
    if user is None or user.deleted_at is not None or not user.is_active:
        raise not_found("USER_NOT_FOUND", "User not found")
    return await get_profile_stats(db, user)
