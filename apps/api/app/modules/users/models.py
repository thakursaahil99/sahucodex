from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, utcnow


class RoleName(enum.StrEnum):
    USER = "USER"
    MODERATOR = "MODERATOR"
    ADMIN = "ADMIN"


class Role(Base):
    """Reference table, seeded by the migration. The name is the primary key."""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    description: Mapped[str] = mapped_column(String(200))


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        # Usernames are unique case-insensitively ("Sahil" and "sahil" cannot both exist).
        Index("uq_users_username_lower", func.lower(text("username")), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)  # stored lower-cased
    username: Mapped[str] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    email_verified_at: Mapped[datetime | None]
    last_login_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]  # soft delete

    profile: Mapped[UserProfile] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="joined", uselist=False
    )
    role_links: Mapped[list[UserRole]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="UserRole.user_id",
    )

    @property
    def roles(self) -> list[str]:
        return sorted(link.role_name for link in self.role_links)

    def has_role(self, *names: str) -> bool:
        return any(name in self.roles for name in names)

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None


class UserProfile(Base, TimestampMixin):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    bio: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(2))  # ISO 3166-1 alpha-2
    website: Mapped[str | None] = mapped_column(String(300))
    github_url: Mapped[str | None] = mapped_column(String(300))

    user: Mapped[User] = relationship(back_populates="profile")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_name: Mapped[str] = mapped_column(ForeignKey("roles.name", ondelete="RESTRICT"), primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    user: Mapped[User] = relationship(back_populates="role_links", foreign_keys=[user_id])
