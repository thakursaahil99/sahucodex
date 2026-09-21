from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import DbSession
from app.core.errors import not_found
from app.modules.auth.deps import CurrentUser
from app.modules.users import service
from app.modules.users.schemas import ProfileUpdate, PublicProfile, UserMe, to_public_profile, to_user_me

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMe)
async def get_me(user: CurrentUser) -> UserMe:
    return to_user_me(user)


@router.patch("/me", response_model=UserMe)
async def update_me(body: ProfileUpdate, user: CurrentUser, db: DbSession) -> UserMe:
    await service.update_profile(db, user, body)
    return to_user_me(user)


# Declared after /me so "me" is never interpreted as a username.
@router.get("/{username}", response_model=PublicProfile)
async def get_public_profile(username: str, db: DbSession) -> PublicProfile:
    user = await service.get_by_username(db, username)
    if user is None or user.deleted_at is not None or not user.is_active:
        raise not_found("USER_NOT_FOUND", "User not found")
    return to_public_profile(user)
