"""Problem platform: problems, tags, examples, test cases, starter code, languages, progress.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must stay in sync with app/modules/problems/search.py (the query has to match this expression to use the index).
FTS_INDEX_EXPRESSION = (
    "setweight(to_tsvector('english'::regconfig, coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english'::regconfig, coalesce(description, '')), 'B')"
)


def _ts(name: str, *, nullable: bool = True, default_now: bool = False) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=nullable, server_default=sa.func.now() if default_now else None
    )


def upgrade() -> None:
    languages = op.create_table(
        "programming_languages",
        sa.Column("key", sa.String(20), nullable=False),
        sa.Column("display_name", sa.String(60), nullable=False),
        sa.Column("editor_language", sa.String(30), nullable=False),
        sa.Column("file_extension", sa.String(10), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_programming_languages")),
    )
    op.bulk_insert(
        languages,
        [
            {"key": "python", "display_name": "Python 3", "editor_language": "python", "file_extension": "py", "sort_order": 1, "is_enabled": True},
            {"key": "cpp", "display_name": "C++17", "editor_language": "cpp", "file_extension": "cpp", "sort_order": 2, "is_enabled": True},
            {"key": "javascript", "display_name": "JavaScript (Node.js)", "editor_language": "javascript", "file_extension": "js", "sort_order": 3, "is_enabled": True},
        ],
    )  # fmt: skip

    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("slug", sa.String(40), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("name", name=op.f("uq_tags_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_tags_slug")),
    )

    op.create_table(
        "problems",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(10), nullable=False),
        sa.Column("constraints", sa.Text(), nullable=False),
        sa.Column("input_format", sa.Text(), nullable=False),
        sa.Column("output_format", sa.Text(), nullable=False),
        sa.Column("time_limit_ms", sa.Integer(), nullable=False, server_default=sa.text("2000")),
        sa.Column("memory_limit_mb", sa.Integer(), nullable=False, server_default=sa.text("256")),
        sa.Column("editorial", sa.Text(), nullable=True),
        sa.Column("hints", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("function_signature", sa.String(300), nullable=True),
        sa.Column("expected_time_complexity", sa.String(60), nullable=True),
        sa.Column("expected_space_complexity", sa.String(60), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        _ts("published_at"),
        _ts("archived_at"),
        sa.Column("total_submissions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("accepted_submissions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        _ts("created_at", nullable=False, default_now=True),
        _ts("updated_at", nullable=False, default_now=True),
        sa.CheckConstraint("time_limit_ms BETWEEN 100 AND 10000", name=op.f("ck_problems_time_limit_range")),
        sa.CheckConstraint("memory_limit_mb BETWEEN 16 AND 1024", name=op.f("ck_problems_memory_limit_range")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_problems_created_by_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_problems")),
        sa.UniqueConstraint("slug", name=op.f("uq_problems_slug")),
    )  # fmt: skip
    op.create_index("ix_problems_listing", "problems", ["published", "archived_at", "difficulty"])
    if op.get_bind().dialect.name == "postgresql":
        # Full-text search over title (weight A) and description (weight B). Other databases fall back to LIKE.
        op.execute(f"CREATE INDEX ix_problems_fts ON problems USING gin (({FTS_INDEX_EXPRESSION}))")

    op.create_table(
        "problem_tags",
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name=op.f("fk_problem_tags_problem_id_problems"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], name=op.f("fk_problem_tags_tag_id_tags"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("problem_id", "tag_id", name=op.f("pk_problem_tags")),
    )  # fmt: skip
    op.create_index(op.f("ix_problem_tags_tag_id"), "problem_tags", ["tag_id"])

    op.create_table(
        "problem_test_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("input_data", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=False),
        _ts("created_at", nullable=False, default_now=True),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name=op.f("fk_problem_test_cases_problem_id_problems"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_problem_test_cases")),
    )  # fmt: skip
    op.create_index("ix_problem_test_cases_problem_kind", "problem_test_cases", ["problem_id", "kind", "position"])

    op.create_table(
        "problem_examples",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("test_case_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name=op.f("fk_problem_examples_problem_id_problems"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_case_id"], ["problem_test_cases.id"], name=op.f("fk_problem_examples_test_case_id_problem_test_cases"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_problem_examples")),
        sa.UniqueConstraint("test_case_id", name=op.f("uq_problem_examples_test_case_id")),
    )  # fmt: skip
    op.create_index(op.f("ix_problem_examples_problem_id"), "problem_examples", ["problem_id"])

    op.create_table(
        "problem_starter_code",
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("language_key", sa.String(20), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name=op.f("fk_problem_starter_code_problem_id_problems"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["language_key"], ["programming_languages.key"], name=op.f("fk_problem_starter_code_language_key_programming_languages"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("problem_id", "language_key", name=op.f("pk_problem_starter_code")),
    )  # fmt: skip

    op.create_table(
        "user_problem_progress",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        _ts("first_solved_at"),
        _ts("last_attempt_at", nullable=False, default_now=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_problem_progress_user_id_users"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], name=op.f("fk_user_problem_progress_problem_id_problems"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "problem_id", name=op.f("pk_user_problem_progress")),
    )  # fmt: skip
    op.create_index("ix_user_problem_progress_problem", "user_problem_progress", ["problem_id", "status"])


def downgrade() -> None:
    op.drop_table("user_problem_progress")
    op.drop_table("problem_starter_code")
    op.drop_table("problem_examples")
    op.drop_table("problem_test_cases")
    op.drop_table("problem_tags")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_problems_fts")
    op.drop_table("problems")
    op.drop_table("tags")
    op.drop_table("programming_languages")
