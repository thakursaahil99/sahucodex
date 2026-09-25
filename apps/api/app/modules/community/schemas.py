"""Request/response models for community: discussions, comments, votes, reports, notifications.

`removed` content is never simply absent from a listing: a removed discussion/comment still appears, with its body
replaced client-side-visibly (see service.py's `_REMOVED_BODY`) so a thread doesn't develop confusing gaps, and the
UI can show "removed by a moderator" rather than the reply just vanishing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TargetType = Literal["discussion", "comment"]


class DiscussionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20_000)


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=10_000)


class VoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Literal[-1, 1]


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2_000)


class AuthorOut(BaseModel):
    id: uuid.UUID | None  # None if the account was deleted (author_id -> NULL, see models.py's ondelete)
    username: str | None


class DiscussionListItem(BaseModel):
    id: uuid.UUID
    title: str
    author: AuthorOut
    vote_score: int
    comment_count: int
    created_at: datetime


class RecentDiscussionItem(DiscussionListItem):
    """Same shape as DiscussionListItem, plus which problem it's under — for the cross-problem `/discussions`
    landing page, where (unlike a problem's own tab) that context isn't already on screen."""

    problem_slug: str
    problem_title: str


class CommentOut(BaseModel):
    id: uuid.UUID
    body: str
    author: AuthorOut
    vote_score: int
    my_vote: int  # -1, 0, or 1 — 0 for an anonymous caller or one who hasn't voted
    removed: bool
    created_at: datetime


class DiscussionDetail(BaseModel):
    id: uuid.UUID
    problem_slug: str
    title: str
    body: str
    author: AuthorOut
    vote_score: int
    my_vote: int
    removed: bool
    locked: bool
    created_at: datetime
    comments: list[CommentOut]


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    data: dict[str, Any]
    read: bool
    created_at: datetime


class UnreadCountOut(BaseModel):
    count: int


# --- admin / moderation --------------------------------------------------------------------------------------------


class ReportOut(BaseModel):
    id: uuid.UUID
    target_type: TargetType
    target_id: uuid.UUID
    reporter: AuthorOut
    reason: str
    status: str
    created_at: datetime
    # Enough to moderate from the reports queue without a second fetch per row.
    target_snippet: str | None  # None if the target was already deleted out from under the report
    target_removed: bool


class ReportResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["remove_content", "dismiss"]
