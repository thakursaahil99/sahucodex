"""Foundation: users, roles, profiles, sessions, one-time tokens, audit log.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp(
    name: str, *, nullable: bool = True, default_now: bool = False
) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=sa.func.now() if default_now else None,
    )


def upgrade() -> None:
    roles = op.create_table(
        "roles",
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_roles")),
    )
    op.bulk_insert(
        roles,
        [
            {
                "name": "USER",
                "description": "Regular member: solve problems, join contests, use the AI assistant",
            },
            {"name": "MODERATOR", "description": "Moderates discussions and reports"},
            {"name": "ADMIN", "description": "Full platform administration"},
        ],
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("username", sa.String(30), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _timestamp("email_verified_at"),
        _timestamp("last_login_at"),
        _timestamp("deleted_at"),
        _timestamp("created_at", nullable=False, default_now=True),
        _timestamp("updated_at", nullable=False, default_now=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    # Case-insensitive uniqueness: "Sahil" and "sahil" cannot both exist.
    op.create_index(
        "uq_users_username_lower", "users", [sa.text("lower(username)")], unique=True
    )

    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("website", sa.String(300), nullable=True),
        sa.Column("github_url", sa.String(300), nullable=True),
        _timestamp("created_at", nullable=False, default_now=True),
        _timestamp("updated_at", nullable=False, default_now=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_profiles")),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_name", sa.String(32), nullable=False),
        _timestamp("granted_at", nullable=False, default_now=True),
        sa.Column("granted_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_roles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_name"],
            ["roles.name"],
            name=op.f("fk_user_roles_role_name_roles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"],
            ["users.id"],
            name=op.f("fk_user_roles_granted_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("user_id", "role_name", name=op.f("pk_user_roles")),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        _timestamp("created_at", nullable=False, default_now=True),
        _timestamp("expires_at", nullable=False),
        _timestamp("revoked_at"),
        sa.Column("revoked_reason", sa.String(32), nullable=True),
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_tokens.id"],
            name=op.f("fk_refresh_tokens_replaced_by_id_refresh_tokens"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_refresh_tokens_family_id"), "refresh_tokens", ["family_id"]
    )
    op.create_index(
        "ix_refresh_tokens_user_active", "refresh_tokens", ["user_id", "revoked_at"]
    )

    op.create_table(
        "one_time_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        _timestamp("created_at", nullable=False, default_now=True),
        _timestamp("expires_at", nullable=False),
        _timestamp("used_at"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_one_time_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_one_time_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_one_time_tokens_token_hash")),
    )
    op.create_index(
        "ix_one_time_tokens_user_purpose", "one_time_tokens", ["user_id", "purpose"]
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        _timestamp("created_at", nullable=False, default_now=True),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        op.f("ix_audit_logs_actor_user_id"), "audit_logs", ["actor_user_id"]
    )
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"])
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_target", "audit_logs", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("one_time_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("user_roles")
    op.drop_table("user_profiles")
    op.drop_index("uq_users_username_lower", table_name="users")
    op.drop_table("users")
    op.drop_table("roles")
