"""Public community API: per-problem discussions and comments, voting, reporting, and a user's own notifications.

Moderation (the reports queue, resolving a report) lives in `app.modules.admin.community`, mounted under the
ADMIN/MODERATOR-guarded `/admin` router — same split as problems and contests.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status

from app.core.deps import DbSession, SettingsDep
from app.core.pagination import Page, PageParamsDep
from app.core.rate_limit import get_rate_limiter
from app.modules.auth.deps import CurrentUser, OptionalUser
from app.modules.community import service as svc
from app.modules.community.schemas import (
    CommentCreate,
    CommentOut,
    DiscussionCreate,
    DiscussionDetail,
    DiscussionListItem,
    NotificationOut,
    RecentDiscussionItem,
    ReportCreate,
    TargetType,
    UnreadCountOut,
    VoteInput,
)

router = APIRouter(tags=["community"])


@router.get("/discussions", response_model=Page[RecentDiscussionItem])
async def list_recent_discussions(db: DbSession, params: PageParamsDep) -> Page[RecentDiscussionItem]:
    """Cross-problem feed for the `/discussions` landing page. Registered before the parameterized
    `/discussions/{discussion_id}` route only for readability — FastAPI already matches static path segments
    before parameterized ones, so the order here doesn't actually affect routing."""
    return await svc.list_recent_discussions(db, params)


@router.get("/problems/{slug}/discussions", response_model=list[DiscussionListItem])
async def list_discussions(slug: str, db: DbSession) -> list[DiscussionListItem]:
    return await svc.list_discussions(db, slug)


@router.post(
    "/problems/{slug}/discussions", response_model=DiscussionListItem, status_code=status.HTTP_201_CREATED
)
async def create_discussion(
    slug: str, data: DiscussionCreate, request: Request, user: CurrentUser, db: DbSession, settings: SettingsDep
) -> DiscussionListItem:
    await get_rate_limiter(request).enforce("community_post", str(user.id), settings.rate_limit_community_post)
    return await svc.create_discussion(db, slug, user, data.title, data.body)


@router.get("/discussions/{discussion_id}", response_model=DiscussionDetail)
async def get_discussion(discussion_id: uuid.UUID, db: DbSession, user: OptionalUser) -> DiscussionDetail:
    return await svc.get_discussion_detail(db, discussion_id, user)


@router.post("/discussions/{discussion_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
async def add_comment(
    discussion_id: uuid.UUID,
    data: CommentCreate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
) -> CommentOut:
    await get_rate_limiter(request).enforce("community_post", str(user.id), settings.rate_limit_community_post)
    return await svc.add_comment(db, discussion_id, user, data.body)


@router.put("/community/{target_type}/{target_id}/vote", status_code=status.HTTP_204_NO_CONTENT)
async def vote(target_type: TargetType, target_id: uuid.UUID, data: VoteInput, user: CurrentUser, db: DbSession) -> None:
    await svc.cast_vote(db, target_type, target_id, user, data.value)


@router.delete("/community/{target_type}/{target_id}/vote", status_code=status.HTTP_204_NO_CONTENT)
async def unvote(target_type: TargetType, target_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    await svc.remove_vote(db, target_type, target_id, user)


@router.post("/community/{target_type}/{target_id}/report", status_code=status.HTTP_204_NO_CONTENT)
async def report(
    target_type: TargetType,
    target_id: uuid.UUID,
    data: ReportCreate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    settings: SettingsDep,
) -> None:
    await get_rate_limiter(request).enforce("community_report", str(user.id), settings.rate_limit_community_report)
    await svc.create_report(db, target_type, target_id, user, data.reason)


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    user: CurrentUser, db: DbSession, unread_only: bool = Query(False)
) -> list[NotificationOut]:
    return await svc.list_notifications(db, user, unread_only)


@router.get("/notifications/unread-count", response_model=UnreadCountOut)
async def unread_count(user: CurrentUser, db: DbSession) -> UnreadCountOut:
    return UnreadCountOut(count=await svc.unread_count(db, user))


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(notification_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    await svc.mark_read(db, user, notification_id)


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(user: CurrentUser, db: DbSession) -> None:
    await svc.mark_all_read(db, user)
