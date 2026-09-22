"""Contests: contests, their problems, participants, and a contest_id tag on submissions.

Revision ID: 0007
Revises: 0006_lang
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006_lang"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("penalty_minutes", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_contests_created_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contests")),
        sa.UniqueConstraint("slug", name=op.f("uq_contests_slug")),
    )  # fmt: skip
    op.create_index("ix_contests_published_start", "contests", ["published", "start_time"])

    op.create_table(
        "contest_problems",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contest_id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(4), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False, server_default="100"),
        sa.ForeignKeyConstraint(["contest_id"], ["contests.id"], name=op.f("fk_contest_problems_contest_id_contests"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name=op.f("fk_contest_problems_problem_id_problems"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contest_problems")),
        sa.UniqueConstraint("contest_id", "label", name="uq_contest_problems_contest_label"),
        sa.UniqueConstraint("contest_id", "problem_id", name="uq_contest_problems_contest_problem"),
    )  # fmt: skip

    op.create_table(
        "contest_participants",
        sa.Column("contest_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contest_id"], ["contests.id"], name=op.f("fk_contest_participants_contest_id_contests"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_contest_participants_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("contest_id", "user_id", name=op.f("pk_contest_participants")),
    )  # fmt: skip
    op.create_index("ix_contest_participants_contest", "contest_participants", ["contest_id"])

    # batch_alter_table: plain add_column + create_foreign_key errors on SQLite ("no support for ALTER of
    # constraints"); batch mode rebuilds the table under the hood there and is a normal ALTER everywhere else.
    with op.batch_alter_table("submissions") as batch:
        batch.add_column(sa.Column("contest_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_submissions_contest_id_contests"), "contests", ["contest_id"], ["id"], ondelete="SET NULL"
        )
    op.create_index("ix_submissions_contest_user_problem", "submissions", ["contest_id", "user_id", "problem_id"])


def downgrade() -> None:
    op.drop_index("ix_submissions_contest_user_problem", table_name="submissions")
    with op.batch_alter_table("submissions") as batch:
        batch.drop_constraint(op.f("fk_submissions_contest_id_contests"), type_="foreignkey")
        batch.drop_column("contest_id")
    op.drop_table("contest_participants")
    op.drop_table("contest_problems")
    op.drop_table("contests")
