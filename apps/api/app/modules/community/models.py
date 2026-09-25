"""Community: per-problem discussion threads, comments, votes, reports, and notifications.

A discussion belongs to exactly one problem (no general/global forum - see docs/README's phase-7 scope note).
Votes are one row per (voter, target) so a re-vote updates in place rather than accumulating; `vote_score` is kept
denormalized on the thread/comment itself (see `service.py`) so listing pages never need a join+aggregate per row.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UTCDateTime


class ReportStatus(enum.StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class Discussion(Base, TimestampMixin):
    """One thread under one problem. `body` is the opening post; replies are `DiscussionComment` rows."""

    __tablename__ = "discussions"
    __table_args__ = (
        Index("ix_discussions_problem_created", "problem_id", "created_at"),
        CheckConstraint("length(title) BETWEEN 1 AND 200", name="title_length"),
        CheckConstraint("length(body) BETWEEN 1 AND 20000", name="body_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)  # Markdown, same convention as problem descriptions
    vote_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    comment_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    # A moderator/admin action (see app.modules.admin.community); the author is never notified why beyond this flag
    # being visible to them - the report that caused it, if any, stays staff-only.
    removed: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # A moderator/admin action, independent of `removed` and not tied to any report - blocks new comments but
    # keeps the thread and its existing comments visible.
    locked: Mapped[bool] = mapped_column(default=False, server_default=text("false"))

    comments: Mapped[list[DiscussionComment]] = relationship(back_populates="discussion", cascade="all, delete-orphan")


class DiscussionComment(Base, TimestampMixin):
    __tablename__ = "discussion_comments"
    __table_args__ = (
        Index("ix_discussion_comments_discussion_created", "discussion_id", "created_at"),
        CheckConstraint("length(body) BETWEEN 1 AND 10000", name="body_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    discussion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("discussions.id", ondelete="CASCADE"))
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    vote_score: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    removed: Mapped[bool] = mapped_column(default=False, server_default=text("false"))

    discussion: Mapped[Discussion] = relationship(back_populates="comments")


class DiscussionVote(Base):
    """One row per (user, target). `target_type` + `target_id` rather than two nullable FKs, so a single unique
    constraint covers both a discussion vote and a comment vote without two near-identical tables."""

    __tablename__ = "discussion_votes"
    __table_args__ = (
        UniqueConstraint("user_id", "target_type", "target_id", name="uq_discussion_votes_user_target"),
        CheckConstraint("target_type IN ('discussion', 'comment')", name="target_type_valid"),
        CheckConstraint("value IN (-1, 1)", name="value_valid"),
        Index("ix_discussion_votes_target", "target_type", "target_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    target_type: Mapped[str] = mapped_column(String(10))  # "discussion" | "comment"
    target_id: Mapped[uuid.UUID] = mapped_column()
    value: Mapped[int] = mapped_column(SmallInteger)  # +1 or -1; no 0 row (removing a vote deletes the row)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())


class Report(Base, TimestampMixin):
    """A flag on a discussion or a comment, raised by any signed-in user. `status` starts OPEN and is moved by a
    moderator/admin (see app.modules.admin.community); reports are never auto-actioned."""

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("target_type IN ('discussion', 'comment')", name="target_type_valid"),
        CheckConstraint("length(reason) BETWEEN 1 AND 2000", name="reason_length"),
        Index("ix_reports_status_created", "status", "created_at"),
        Index("ix_reports_target", "target_type", "target_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    target_type: Mapped[str] = mapped_column(String(10))
    target_id: Mapped[uuid.UUID] = mapped_column()
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default=ReportStatus.OPEN.value, server_default=text("'OPEN'"))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class NotificationType(enum.StrEnum):
    DISCUSSION_REPLY = "DISCUSSION_REPLY"  # someone replied to a thread you started
    COMMENT_REPLY = "COMMENT_REPLY"  # not used yet (comments aren't threaded) - reserved for a future nested reply
    CONTENT_REMOVED = "CONTENT_REMOVED"  # a moderator removed your discussion or comment


class Notification(Base):
    """In-app only (no email/push - see docs/community.md). `data` carries just enough to build the link and
    message client-side (e.g. {"discussion_id": ..., "problem_slug": ..., "actor_username": ...}) without a join at
    read time; nothing in it is ever sensitive, since notifications are rendered as plain in-app list items."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'"))
    read: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), server_default=func.now())
