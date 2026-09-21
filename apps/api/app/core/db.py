"""Database primitives: declarative base, portable column types, mixins, engine factory."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import JSON, DateTime, MetaData, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

from app.core.config import Settings

# Stable constraint names keep Alembic migrations deterministic across databases.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# Indexes Alembic cannot compare (PostgreSQL expression/GIN indexes). They exist only in migrations, so the
# model-vs-migration drift check must ignore them. Used by database/migrations/env.py and the migration test.
MIGRATION_ONLY_INDEXES = frozenset({"ix_problems_fts"})


def include_object(obj: object, name: str | None, type_: str, reflected: bool, compare_to: object) -> bool:
    return not (type_ == "index" and name in MIGRATION_ONLY_INDEXES)


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """`timestamptz` on PostgreSQL; on SQLite (tests) re-attaches UTC to the naive value it returns."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


# JSONB on PostgreSQL (indexable), plain JSON elsewhere.
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: UTCDateTime(), uuid.UUID: Uuid(as_uuid=True), dict[str, Any]: JsonType}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, server_default=func.now()
    )


def create_engine_from_settings(settings: Settings) -> AsyncEngine:
    if settings.database_url.startswith("sqlite"):
        # In-memory SQLite (tests) needs one shared connection.
        return create_async_engine(
            settings.database_url,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
            echo=settings.db_echo,
        )
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        echo=settings.db_echo,
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Request-scoped session. Services commit explicitly; anything uncommitted is rolled back."""
    async with request.app.state.sessionmaker() as session:
        yield session
