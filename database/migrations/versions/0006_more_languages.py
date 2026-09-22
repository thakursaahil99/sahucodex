"""More judge languages: C, Java, C#, Go, Rust, TypeScript, PHP.

Idempotent upsert (not a straight bulk_insert) so it is safe to run against a database that already has some of
these rows from manual testing, and the downgrade only removes the rows it added.

Revision ID: 0006_lang
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_lang"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_LANGUAGES = [
    {"key": "c", "display_name": "C17", "editor_language": "c", "file_extension": "c", "sort_order": 4},
    {"key": "java", "display_name": "Java 21", "editor_language": "java", "file_extension": "java", "sort_order": 5},
    {"key": "csharp", "display_name": "C# 12", "editor_language": "csharp", "file_extension": "cs", "sort_order": 6},
    {"key": "go", "display_name": "Go 1.23", "editor_language": "go", "file_extension": "go", "sort_order": 7},
    {"key": "rust", "display_name": "Rust (stable)", "editor_language": "rust", "file_extension": "rs", "sort_order": 8},
    {
        "key": "typescript",
        "display_name": "TypeScript",
        "editor_language": "typescript",
        "file_extension": "ts",
        "sort_order": 9,
    },
    {"key": "php", "display_name": "PHP 8", "editor_language": "php", "file_extension": "php", "sort_order": 10},
]


def upgrade() -> None:
    languages = sa.table(
        "programming_languages",
        sa.column("key", sa.String),
        sa.column("display_name", sa.String),
        sa.column("editor_language", sa.String),
        sa.column("file_extension", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_enabled", sa.Boolean),
    )
    connection = op.get_bind()
    existing = {row[0] for row in connection.execute(sa.select(languages.c.key))}
    to_insert = [{**row, "is_enabled": True} for row in NEW_LANGUAGES if row["key"] not in existing]
    if to_insert:
        op.bulk_insert(languages, to_insert)


def downgrade() -> None:
    keys = [row["key"] for row in NEW_LANGUAGES]
    statement = sa.text("DELETE FROM programming_languages WHERE key IN :keys").bindparams(
        sa.bindparam("keys", expanding=True)
    )
    op.get_bind().execute(statement, {"keys": keys})
