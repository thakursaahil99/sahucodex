"""Profiles: streaks, the achievement catalogue, earned achievements.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep in sync with app/modules/profiles/achievements.py: every CHECKS key must have a row here (a test guards this).
ACHIEVEMENTS = [
    {"key": "first_solve", "name": "First Blood", "description": "Solve your first problem.", "icon": "Sparkles", "sort_order": 1},
    {"key": "ten_solved", "name": "Problem Solver", "description": "Solve 10 problems.", "icon": "Trophy", "sort_order": 2},
    {"key": "all_difficulties", "name": "Well Rounded", "description": "Solve at least one Easy, one Medium and one Hard problem.", "icon": "Layers", "sort_order": 3},
    {"key": "polyglot", "name": "Polyglot", "description": "Get an accepted submission in two different languages.", "icon": "Languages", "sort_order": 4},
    {"key": "topic_explorer", "name": "Topic Explorer", "description": "Solve problems across 10 different topics.", "icon": "Compass", "sort_order": 5},
    {"key": "streak_7", "name": "One Week Streak", "description": "Reach a 7-day solving streak.", "icon": "Flame", "sort_order": 6},
    {"key": "streak_30", "name": "One Month Streak", "description": "Reach a 30-day solving streak.", "icon": "CalendarCheck", "sort_order": 7},
    {"key": "hundred_submissions", "name": "Persistent", "description": "Make 100 submissions.", "icon": "Target", "sort_order": 8},
]  # fmt: skip


def upgrade() -> None:
    op.create_table(
        "user_streaks",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("current_streak", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("longest_streak", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_active_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_streaks_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_streaks")),
    )  # fmt: skip

    achievements = op.create_table(
        "achievements",
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(40), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_achievements")),
    )
    op.bulk_insert(achievements, ACHIEVEMENTS)

    op.create_table(
        "user_achievements",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("achievement_key", sa.String(40), nullable=False),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_achievements_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["achievement_key"], ["achievements.key"], name=op.f("fk_user_achievements_achievement_key_achievements"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "achievement_key", name=op.f("pk_user_achievements")),
    )  # fmt: skip


def downgrade() -> None:
    op.drop_table("user_achievements")
    op.drop_table("achievements")
    op.drop_table("user_streaks")
