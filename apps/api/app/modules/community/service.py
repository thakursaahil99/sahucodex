"""Community use cases: discussions, comments, voting, reports, notifications.

**Voting** is stored as one row per (user, target) in `discussion_votes`; the target's own `vote_score` is kept
denormalized (updated in the same transaction as the vote) so every listing page reads one integer column instead of
a join+SUM per row. **Reports** never auto-remove anything — a moderator/admin always makes the call
(`app.modules.admin.community`). **Notifications** are in-app only, written best-effort in the same transaction as
the action that causes them (a reply): if that write fails the surrounding action still succeeds, since a missed
notification is not worth failing someone's comment over.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.core.errors import AppError, not_found
from app.core.pagination import Page, PageParams
from app.modules.community.models import (
    Discussion,
    DiscussionComment,
    DiscussionVote,
    Notification,
    NotificationType,
    Report,
    ReportStatus,
)
from app.modules.community.schemas import (
    AuthorOut,
    CommentOut,
    DiscussionDetail,
    DiscussionListItem,
    NotificationOut,
    RecentDiscussionItem,
    ReportOut,
)
from app.modules.problems.models import Problem
from app.modules.problems.service import find_visible_problem
from app.modules.users.models import User

_REMOVED_BODY = "[removed by a moderator]"


def _author_out(user_id: uuid.UUID | None, username: str | None) -> AuthorOut:
    return AuthorOut(id=user_id, username=username)


async def _my_vote(db: AsyncSession, user: User | None, target_type: str, target_id: uuid.UUID) -> int:
    if user is None:
        return 0
    value = await db.scalar(
        select(DiscussionVote.value).where(
            DiscussionVote.user_id == user.id,
            DiscussionVote.target_type == target_type,
            DiscussionVote.target_id == target_id,
        )
    )
    return value or 0


# --- discussions -----------------------------------------------------------------------------------------------


async def list_discussions(db: AsyncSession, problem_slug: str) -> list[DiscussionListItem]:
    problem = await find_visible_problem(db, problem_slug)
    if problem is None:
        raise not_found("PROBLEM_NOT_FOUND", "No such problem")
    rows = (
        await db.execute(
            select(Discussion, User.username)
            .outerjoin(User, User.id == Discussion.author_id)
            .where(Discussion.problem_id == problem.id)
            .order_by(Discussion.created_at.desc())
        )
    ).all()
    return [
        DiscussionListItem(
            id=d.id,
            title=d.title,
            author=_author_out(d.author_id, username),
            vote_score=d.vote_score,
            comment_count=d.comment_count,
            created_at=d.created_at,
        )
        for d, username in rows
    ]


async def list_recent_discussions(db: AsyncSession, params: PageParams) -> Page[RecentDiscussionItem]:
    """Cross-problem feed for the `/discussions` landing page — a problem's own tab (`list_discussions`) doesn't
    need the problem's own title/slug on each row since that's already on screen; this does."""
    # Same visibility rule as find_visible_problem: a discussion under an unpublished/archived problem must not
    # leak that problem's title/slug (or its existence) into this public cross-problem feed.
    base = (
        select(Discussion, User.username, Problem.slug, Problem.title)
        .outerjoin(User, User.id == Discussion.author_id)
        .join(Problem, Problem.id == Discussion.problem_id)
        .where(Problem.published.is_(True), Problem.archived_at.is_(None))
    )

    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (
        await db.execute(base.order_by(Discussion.created_at.desc()).offset(params.offset).limit(params.limit))
    ).all()
    items = [
        RecentDiscussionItem(
            id=d.id,
            title=d.title,
            author=_author_out(d.author_id, username),
            vote_score=d.vote_score,
            comment_count=d.comment_count,
            created_at=d.created_at,
            problem_slug=problem_slug,
            problem_title=problem_title,
        )
        for d, username, problem_slug, problem_title in rows
    ]
    return Page.build(items, total or 0, params)


async def create_discussion(
    db: AsyncSession, problem_slug: str, user: User, title: str, body: str
) -> DiscussionListItem:
    problem = await find_visible_problem(db, problem_slug)
    if problem is None:
        raise not_found("PROBLEM_NOT_FOUND", "No such problem")
    discussion = Discussion(problem_id=problem.id, author_id=user.id, title=title, body=body)
    db.add(discussion)
    await db.flush()
    await db.commit()
    return DiscussionListItem(
        id=discussion.id,
        title=discussion.title,
        author=_author_out(user.id, user.username),
        vote_score=0,
        comment_count=0,
        created_at=discussion.created_at,
    )


async def _get_discussion(db: AsyncSession, discussion_id: uuid.UUID) -> Discussion:
    discussion = await db.get(Discussion, discussion_id)
    if discussion is None:
        raise not_found("DISCUSSION_NOT_FOUND", "No such discussion")
    return discussion


async def get_discussion_detail(db: AsyncSession, discussion_id: uuid.UUID, user: User | None) -> DiscussionDetail:
    discussion = await _get_discussion(db, discussion_id)
    author_row = await db.execute(select(User.username, User.id).where(User.id == discussion.author_id))
    author = author_row.first()

    problem = await db.get(Problem, discussion.problem_id)

    comment_rows = (
        await db.execute(
            select(DiscussionComment, User.username)
            .outerjoin(User, User.id == DiscussionComment.author_id)
            .where(DiscussionComment.discussion_id == discussion_id)
            .order_by(DiscussionComment.created_at.asc())
        )
    ).all()

    comments: list[CommentOut] = []
    for comment, username in comment_rows:
        my_vote = await _my_vote(db, user, "comment", comment.id)
        comments.append(
            CommentOut(
                id=comment.id,
                body=_REMOVED_BODY if comment.removed else comment.body,
                author=_author_out(comment.author_id, username),
                vote_score=comment.vote_score,
                my_vote=my_vote,
                removed=comment.removed,
                created_at=comment.created_at,
            )
        )

    my_vote = await _my_vote(db, user, "discussion", discussion.id)
    return DiscussionDetail(
        id=discussion.id,
        problem_slug=problem.slug if problem else "",
        title=discussion.title,
        body=_REMOVED_BODY if discussion.removed else discussion.body,
        author=_author_out(discussion.author_id, author[0] if author else None),
        vote_score=discussion.vote_score,
        my_vote=my_vote,
        removed=discussion.removed,
        locked=discussion.locked,
        created_at=discussion.created_at,
        comments=comments,
    )


async def add_comment(db: AsyncSession, discussion_id: uuid.UUID, user: User, body: str) -> CommentOut:
    discussion = await _get_discussion(db, discussion_id)
    if discussion.locked:
        raise AppError(409, "DISCUSSION_LOCKED", "This discussion is locked and no longer accepts replies")
    comment = DiscussionComment(discussion_id=discussion_id, author_id=user.id, body=body)
    db.add(comment)
    discussion.comment_count += 1
    await db.flush()

    if discussion.author_id is not None and discussion.author_id != user.id:
        await _notify(
            db,
            discussion.author_id,
            NotificationType.DISCUSSION_REPLY,
            {
                "discussion_id": str(discussion.id),
                "discussion_title": discussion.title,
                "actor_username": user.username,
            },
        )
    await db.commit()
    return CommentOut(
        id=comment.id,
        body=comment.body,
        author=_author_out(user.id, user.username),
        vote_score=0,
        my_vote=0,
        removed=False,
        created_at=comment.created_at,
    )


# --- voting ----------------------------------------------------------------------------------------------------


async def _target_model(target_type: str) -> type[Discussion] | type[DiscussionComment]:
    return Discussion if target_type == "discussion" else DiscussionComment


async def cast_vote(db: AsyncSession, target_type: str, target_id: uuid.UUID, user: User, value: int) -> int:
    """Upserts the caller's vote and returns the target's new `vote_score`. `value=0` (delete the vote) is handled
    by `remove_vote` instead, so this only ever writes +1/-1 - the schema's `VoteInput` already rejects 0."""
    model = await _target_model(target_type)
    target = await db.get(model, target_id)
    if target is None:
        raise not_found("NOT_FOUND", f"No such {target_type}")

    existing = await db.scalar(
        select(DiscussionVote).where(
            DiscussionVote.user_id == user.id,
            DiscussionVote.target_type == target_type,
            DiscussionVote.target_id == target_id,
        )
    )
    if existing is None:
        db.add(DiscussionVote(user_id=user.id, target_type=target_type, target_id=target_id, value=value))
        target.vote_score += value
    elif existing.value != value:
        target.vote_score += value - existing.value
        existing.value = value
    # else: identical vote resubmitted — no-op, matches the idempotent PUT semantics of the route.
    await db.commit()
    return target.vote_score


async def remove_vote(db: AsyncSession, target_type: str, target_id: uuid.UUID, user: User) -> int:
    model = await _target_model(target_type)
    target = await db.get(model, target_id)
    if target is None:
        raise not_found("NOT_FOUND", f"No such {target_type}")
    existing = await db.scalar(
        select(DiscussionVote).where(
            DiscussionVote.user_id == user.id,
            DiscussionVote.target_type == target_type,
            DiscussionVote.target_id == target_id,
        )
    )
    if existing is not None:
        target.vote_score -= existing.value
        await db.delete(existing)
    await db.commit()
    return target.vote_score


# --- reports -----------------------------------------------------------------------------------------------------


async def create_report(db: AsyncSession, target_type: str, target_id: uuid.UUID, user: User, reason: str) -> None:
    model = await _target_model(target_type)
    target = await db.get(model, target_id)
    if target is None:
        raise not_found("NOT_FOUND", f"No such {target_type}")
    db.add(Report(target_type=target_type, target_id=target_id, reporter_id=user.id, reason=reason))
    await db.commit()


async def list_reports(db: AsyncSession, status_filter: str | None) -> list[ReportOut]:
    stmt = select(Report, User.username).outerjoin(User, User.id == Report.reporter_id)
    if status_filter:
        stmt = stmt.where(Report.status == status_filter)
    stmt = stmt.order_by(Report.created_at.desc())
    rows = (await db.execute(stmt)).all()

    # Batch-fetch targets per model type (one query per type, not one per report) to avoid an N+1 on the
    # moderation queue.
    ids_by_type: dict[str, set[uuid.UUID]] = {}
    for report, _ in rows:
        ids_by_type.setdefault(report.target_type, set()).add(report.target_id)
    targets: dict[tuple[str, uuid.UUID], Discussion | DiscussionComment] = {}
    for target_type, ids in ids_by_type.items():
        model = await _target_model(target_type)
        found = (await db.execute(select(model).where(model.id.in_(ids)))).scalars().all()
        for row in found:
            targets[(target_type, row.id)] = row

    out: list[ReportOut] = []
    for report, reporter_username in rows:
        target = targets.get((report.target_type, report.target_id))
        snippet = None
        removed = False
        if target is not None:
            body = getattr(target, "title", None) or getattr(target, "body", "")
            snippet = (body or "")[:200]
            removed = target.removed
        out.append(
            ReportOut(
                id=report.id,
                target_type=report.target_type,  # type: ignore[arg-type]
                target_id=report.target_id,
                reporter=_author_out(report.reporter_id, reporter_username),
                reason=report.reason,
                status=report.status,
                created_at=report.created_at,
                target_snippet=snippet,
                target_removed=removed,
            )
        )
    return out


async def resolve_report(db: AsyncSession, report_id: uuid.UUID, moderator: User, action: str) -> None:
    report = await db.get(Report, report_id)
    if report is None:
        raise not_found("REPORT_NOT_FOUND", "No such report")
    if report.status != ReportStatus.OPEN.value:
        raise AppError(409, "ALREADY_RESOLVED", "This report has already been resolved")

    if action == "remove_content":
        model = await _target_model(report.target_type)
        target = await db.get(model, report.target_id)
        if target is not None and not target.removed:
            target.removed = True
            if target.author_id is not None:
                await _notify(
                    db,
                    target.author_id,
                    NotificationType.CONTENT_REMOVED,
                    {"target_type": report.target_type, "target_id": str(report.target_id)},
                )
        report.status = ReportStatus.RESOLVED.value
    else:
        report.status = ReportStatus.DISMISSED.value
    report.resolved_by = moderator.id
    report.resolved_at = utcnow()
    await db.commit()


async def set_discussion_locked(db: AsyncSession, discussion_id: uuid.UUID, locked: bool) -> None:
    """Independent of `removed`/reports: blocks new comments while keeping the thread and its existing
    comments visible."""
    discussion = await _get_discussion(db, discussion_id)
    discussion.locked = locked
    await db.commit()


# --- notifications ---------------------------------------------------------------------------------------------


async def _notify(db: AsyncSession, user_id: uuid.UUID, type_: NotificationType, data: dict[str, Any]) -> None:
    db.add(Notification(user_id=user_id, type=type_.value, data=data))


async def list_notifications(db: AsyncSession, user: User, unread_only: bool) -> list[NotificationOut]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(100)
    rows = (await db.scalars(stmt)).all()
    return [
        NotificationOut(id=n.id, type=n.type, data=n.data, read=n.read, created_at=n.created_at) for n in rows
    ]


async def unread_count(db: AsyncSession, user: User) -> int:
    count = await db.scalar(
        select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.read.is_(False))
    )
    return count or 0


async def mark_read(db: AsyncSession, user: User, notification_id: uuid.UUID) -> None:
    notification = await db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise not_found("NOTIFICATION_NOT_FOUND", "No such notification")
    notification.read = True
    await db.commit()


async def mark_all_read(db: AsyncSession, user: User) -> None:
    await db.execute(
        update(Notification).where(Notification.user_id == user.id, Notification.read.is_(False)).values(read=True)
    )
    await db.commit()
