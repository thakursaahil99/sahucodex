"""Seed data: one admin, two demo users, the 23 topic tags and the 30 original practice problems.

    python database/seeds/run.py

Credentials come from SEED_* environment variables (see .env.example); nothing secret is hardcoded.
The script is idempotent: existing accounts are left untouched (passwords are never overwritten).

Safety rules
  * Demo users are only created when APP_ENV != production.
  * The admin is created in any environment, but only if SEED_ADMIN_PASSWORD is supplied and
    is at least 12 characters, so a production database can never receive a well-known password.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Works both in the repo (apps/api next to database/) and in the container image (same layout).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for the `catalog` package

import app.db_models  # noqa: F401
from app.core.config import Settings, get_settings
from app.core.db import create_engine_from_settings, create_sessionmaker
from app.modules.users import service as users
from problems_seed import seed_problems
from app.modules.users.models import RoleName, UserRole
from dotenv import dotenv_values

MIN_ADMIN_PASSWORD_LENGTH = 12


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOTENV = dotenv_values(
    _REPO_ROOT / ".env"
)  # empty if there is no .env (e.g. inside a container)


def _env(name: str) -> str | None:
    """Real environment variables win over the repo-root .env file."""
    value = (os.environ.get(name) or _DOTENV.get(name) or "").strip()
    return value or None


async def _seed_user(
    db,
    settings: Settings,
    *,
    email: str,
    username: str,
    password: str,
    roles: list[RoleName],
) -> None:
    existing = await users.get_by_email(db, email) or await users.get_by_username(
        db, username
    )
    if existing is not None:
        missing = [r for r in roles if r not in existing.roles]
        for role in missing:
            db.add(UserRole(user_id=existing.id, role_name=str(role)))
        await db.commit()
        print(
            f"  = {username} already exists"
            + (f" (added roles: {', '.join(missing)})" if missing else "")
        )
        return
    await users.create_user(
        db,
        settings,
        email=email,
        username=username,
        password=password,
        roles=roles,
        email_verified=True,
    )
    await db.commit()
    print(f"  + created {username} <{email}> [{', '.join(roles)}]")


async def main() -> int:
    settings = get_settings()
    engine = create_engine_from_settings(settings)
    sessionmaker = create_sessionmaker(engine)
    print(f"Seeding ({settings.app_env})")
    try:
        async with sessionmaker() as db:
            admin_email = _env("SEED_ADMIN_EMAIL")
            admin_password = _env("SEED_ADMIN_PASSWORD")
            if admin_email and admin_password:
                if len(admin_password) < MIN_ADMIN_PASSWORD_LENGTH:
                    print(
                        f"SEED_ADMIN_PASSWORD must be at least {MIN_ADMIN_PASSWORD_LENGTH} characters",
                        file=sys.stderr,
                    )
                    return 1
                await _seed_user(
                    db,
                    settings,
                    email=admin_email,
                    username=_env("SEED_ADMIN_USERNAME") or "sahuadmin",
                    password=admin_password,
                    roles=[RoleName.ADMIN, RoleName.USER],
                )
            else:
                print(
                    "  ! SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD not set - skipping admin"
                )

            if settings.is_production:
                print("  ! production: demo users are never seeded")
            else:
                for index in (1, 2):
                    email = _env(f"SEED_DEMO{index}_EMAIL")
                    password = _env(f"SEED_DEMO{index}_PASSWORD")
                    if email and password:
                        await _seed_user(
                            db,
                            settings,
                            email=email,
                            username=_env(f"SEED_DEMO{index}_USERNAME")
                            or f"demo{index}",
                            password=password,
                            roles=[RoleName.USER],
                        )
                    else:
                        print(
                            f"  ! SEED_DEMO{index}_* not set - skipping demo user {index}"
                        )

            # Content, not credentials: safe in every environment. Set SEED_PROBLEMS=false to skip.
            if (_env("SEED_PROBLEMS") or "true").lower() != "false":
                admin = await users.get_by_email(db, admin_email) if admin_email else None
                created, skipped = await seed_problems(db, created_by=admin.id if admin else None)
                print(f"  + problems: {created} created, {skipped} already present")
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
