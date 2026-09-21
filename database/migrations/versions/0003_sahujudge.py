"""SahuJudge: submissions, their results, per-test outcomes, and the per-problem output checker.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts(name: str, *, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.add_column("problems", sa.Column("checker", sa.String(20), nullable=False, server_default="lines"))

    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("language_key", sa.String(20), nullable=False),
        sa.Column("source_code", sa.Text(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="QUEUED"),
        sa.Column("verdict", sa.String(24), nullable=True),
        sa.Column("runtime_ms", sa.Integer(), nullable=True),
        sa.Column("memory_kb", sa.Integer(), nullable=True),
        sa.Column("passed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        _ts("created_at", nullable=False),
        _ts("started_at"),
        _ts("finished_at"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_submissions_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name=op.f("fk_submissions_problem_id_problems"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["language_key"], ["programming_languages.key"], name=op.f("fk_submissions_language_key_programming_languages"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
    )  # fmt: skip
    op.create_index("ix_submissions_user_created", "submissions", ["user_id", "created_at"])
    op.create_index("ix_submissions_user_problem", "submissions", ["user_id", "problem_id", "created_at"])
    op.create_index("ix_submissions_status_created", "submissions", ["status", "created_at"])

    op.create_table(
        "submission_results",
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("compile_output", sa.Text(), nullable=True),
        sa.Column("message", sa.String(300), nullable=True),
        sa.Column("checker", sa.String(20), nullable=False),
        sa.Column("judge_version", sa.String(20), nullable=False),
        sa.Column("time_limit_ms", sa.Integer(), nullable=False),
        sa.Column("memory_limit_mb", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], name=op.f("fk_submission_results_submission_id_submissions"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("submission_id", name=op.f("pk_submission_results")),
    )  # fmt: skip

    op.create_table(
        "submission_test_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("test_case_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("verdict", sa.String(24), nullable=False),
        sa.Column("runtime_ms", sa.Integer(), nullable=True),
        sa.Column("memory_kb", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], name=op.f("fk_submission_test_results_submission_id_submissions"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_case_id"], ["problem_test_cases.id"], name=op.f("fk_submission_test_results_test_case_id_problem_test_cases"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission_test_results")),
    )  # fmt: skip
    op.create_index("ix_submission_test_results_submission", "submission_test_results", ["submission_id", "position"])


def downgrade() -> None:
    op.drop_table("submission_test_results")
    op.drop_table("submission_results")
    op.drop_table("submissions")
    op.drop_column("problems", "checker")
