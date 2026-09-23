"""Community: per-problem discussions, comments, votes, reports, and notifications.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discussions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("vote_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("removed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(title) BETWEEN 1 AND 200", name=op.f("ck_discussions_title_length")),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 20000", name=op.f("ck_discussions_body_length")),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name=op.f("fk_discussions_problem_id_problems"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name=op.f("fk_discussions_author_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discussions")),
    )  # fmt: skip
    op.create_index("ix_discussions_problem_created", "discussions", ["problem_id", "created_at"])

    op.create_table(
        "discussion_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("discussion_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("vote_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("removed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 10000", name=op.f("ck_discussion_comments_body_length")),
        sa.ForeignKeyConstraint(["discussion_id"], ["discussions.id"], name=op.f("fk_discussion_comments_discussion_id_discussions"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name=op.f("fk_discussion_comments_author_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discussion_comments")),
    )  # fmt: skip
    op.create_index("ix_discussion_comments_discussion_created", "discussion_comments", ["discussion_id", "created_at"])

    op.create_table(
        "discussion_votes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(10), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("value", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("target_type IN ('discussion', 'comment')", name=op.f("ck_discussion_votes_target_type_valid")),
        sa.CheckConstraint("value IN (-1, 1)", name=op.f("ck_discussion_votes_value_valid")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_discussion_votes_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discussion_votes")),
        sa.UniqueConstraint("user_id", "target_type", "target_id", name="uq_discussion_votes_user_target"),
    )  # fmt: skip
    op.create_index("ix_discussion_votes_target", "discussion_votes", ["target_type", "target_id"])

    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(10), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("reporter_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="OPEN"),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("target_type IN ('discussion', 'comment')", name=op.f("ck_reports_target_type_valid")),
        sa.CheckConstraint("length(reason) BETWEEN 1 AND 2000", name=op.f("ck_reports_reason_length")),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], name=op.f("fk_reports_reporter_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], name=op.f("fk_reports_resolved_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
    )  # fmt: skip
    op.create_index("ix_reports_status_created", "reports", ["status", "created_at"])
    op.create_index("ix_reports_target", "reports", ["target_type", "target_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("data", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False, server_default="{}"),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_notifications_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )  # fmt: skip
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("reports")
    op.drop_table("discussion_votes")
    op.drop_table("discussion_comments")
    op.drop_table("discussions")
