from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import utcnow
from app.core.pagination import PageParams
from app.core.security import hash_password
from app.modules.users.models import RoleName, User, UserProfile, UserRole
from app.modules.users.schemas import ProfileUpdate

# Names that would let someone impersonate staff or collide with product routes.
RESERVED_USERNAMES = frozenset(
    {
        "admin", "administrator", "root", "system", "support", "moderator", "mod", "staff",
        "sahucodex", "sahujudge", "sahucodexai", "api", "null", "undefined", "me", "anonymous",
    }
)  # fmt: skip


def normalise_email(email: str) -> str:
    return email.strip().lower()


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == normalise_email(email)))


async def get_by_username(db: AsyncSession, username: str) -> User | None:
    return await db.scalar(select(User).where(func.lower(User.username) == username.lower()))


async def get_by_identifier(db: AsyncSession, identifier: str) -> User | None:
    """Sign-in accepts either an email address or a username."""
    identifier = identifier.strip()
    if "@" in identifier:
        return await get_by_email(db, identifier)
    return await get_by_username(db, identifier)


async def create_user(
    db: AsyncSession,
    settings: Settings,
    *,
    email: str,
    username: str,
    password: str,
    roles: Sequence[RoleName] = (RoleName.USER,),
    email_verified: bool = False,
) -> User:
    """Stages a user, profile and role links. The caller commits."""
    user = User(
        id=uuid.uuid4(),
        email=normalise_email(email),
        username=username,
        password_hash=hash_password(password, settings),
        email_verified_at=utcnow() if email_verified else None,
    )
    user.profile = UserProfile()
    user.role_links = [UserRole(role_name=str(role)) for role in roles]
    db.add(user)
    await db.flush()
    return user


async def update_profile(db: AsyncSession, user: User, changes: ProfileUpdate) -> User:
    # Apply only the fields the client actually sent, so `null` clears a field and omission keeps it.
    for field in changes.model_fields_set:
        setattr(user.profile, field, getattr(changes, field))
    await db.commit()
    return user


async def list_users(db: AsyncSession, params: PageParams, query: str | None) -> tuple[list[User], int]:
    stmt = select(User).where(User.deleted_at.is_(None))
    if query:
        # Escape LIKE wildcards so user input is matched literally.
        escaped = query.lower().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        pattern = f"%{escaped}%"
        stmt = stmt.where(
            or_(func.lower(User.username).like(pattern, escape="\\"), User.email.like(pattern, escape="\\"))
        )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.scalars(stmt.order_by(User.created_at.desc(), User.id).offset(params.offset).limit(params.limit))
    return list(rows.unique()), total
