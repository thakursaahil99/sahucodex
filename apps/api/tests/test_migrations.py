"""The Alembic migrations must build exactly the schema the models describe."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

import app.db_models  # noqa: F401
from app.core.db import Base, include_object
from app.modules.profiles.achievements import CATALOG as ACHIEVEMENT_CATALOG

API_DIR = Path(__file__).resolve().parents[1]


def _postgres_url() -> str | None:
    url = os.environ.get("TEST_DATABASE_URL")
    if url and url.startswith(("postgresql", "postgres")):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
            "postgres://", "postgresql+asyncpg://", 1
        )
    return None


async def _reset_postgres(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


@pytest.fixture(params=["sqlite", "postgres"])
def alembic_config(request, tmp_path) -> tuple[Config, str]:
    if request.param == "postgres":
        url = _postgres_url()
        if url is None:
            pytest.skip("set TEST_DATABASE_URL to a PostgreSQL URL to also verify migrations on PostgreSQL")
        asyncio.run(_reset_postgres(url))
    else:
        url = f"sqlite+aiosqlite:///{tmp_path / 'migrations.db'}"
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR.parents[1] / "database" / "migrations"))
    cfg.attributes["database_url"] = url
    return cfg, url


async def _inspect(url: str):
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
            roles = (await conn.exec_driver_sql("SELECT name FROM roles ORDER BY name")).scalars().all()
            languages = (
                (await conn.exec_driver_sql("SELECT key FROM programming_languages ORDER BY key")).scalars().all()
            )
            achievements = (await conn.exec_driver_sql("SELECT key FROM achievements ORDER BY key")).scalars().all()
            index_sql = (
                "SELECT name FROM sqlite_master WHERE type = 'index'"
                if conn.dialect.name == "sqlite"
                else "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
            )
            indexes = (await conn.exec_driver_sql(index_sql)).scalars().all()
            diff = await conn.run_sync(
                lambda c: compare_metadata(
                    MigrationContext.configure(c, opts={"include_object": include_object}), Base.metadata
                )
            )
            return tables, roles, languages, achievements, indexes, diff
    finally:
        await engine.dispose()


def test_upgrade_builds_the_model_schema_and_seeds_roles(alembic_config):
    cfg, url = alembic_config
    command.upgrade(cfg, "head")
    tables, roles, languages, achievements, indexes, diff = asyncio.run(_inspect(url))

    assert {
        "users",
        "user_profiles",
        "roles",
        "user_roles",
        "refresh_tokens",
        "one_time_tokens",
        "audit_logs",
        "problems",
        "tags",
        "problem_tags",
        "problem_examples",
        "problem_test_cases",
        "problem_starter_code",
        "programming_languages",
        "user_problem_progress",
        "submissions",
        "submission_results",
        "submission_test_results",
        "user_streaks",
        "achievements",
        "user_achievements",
    } <= tables
    assert roles == ["ADMIN", "MODERATOR", "USER"]
    assert languages == ["c", "cpp", "csharp", "go", "java", "javascript", "php", "python", "rust", "typescript"]
    # The migration keeps its own frozen copy of this data (see achievements.py's module docstring for why); this
    # catches the two copies drifting apart in practice, without letting the migration import mutable app code.
    assert achievements == sorted(a.key for a in ACHIEVEMENT_CATALOG)
    # Alembic cannot compare expression indexes on SQLite, so assert this one explicitly.
    assert "uq_users_username_lower" in indexes
    # If this fails, a model changed without a matching migration.
    assert diff == [], diff


def test_downgrade_removes_everything(alembic_config):
    cfg, url = alembic_config
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    tables, *_ = asyncio.run(_inspect_tables(url))
    assert tables <= {"alembic_version"}


async def _inspect_tables(url: str):
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return (await conn.run_sync(lambda c: set(inspect(c).get_table_names())),)
    finally:
        await engine.dispose()
