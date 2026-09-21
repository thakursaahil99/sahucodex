"""A throwaway world for pipeline tests: in-memory SQLite, fakeredis, and whichever sandbox double the test picks."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import fakeredis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.db_models  # noqa: F401
from app.core.config import Settings
from app.core.db import Base, create_engine_from_settings, create_sessionmaker, utcnow
from app.modules.problems.models import (
    CaseKind,
    Problem,
    ProblemExample,
    ProblemTestCase,
    ProgrammingLanguage,
)
from app.modules.profiles.achievements import CATALOG as ACHIEVEMENT_CATALOG
from app.modules.profiles.models import Achievement
from app.modules.submissions import events
from app.modules.submissions.models import Submission, SubmissionStatus
from app.modules.users import service as users
from app.modules.users.models import Role, RoleName
from sahujudge.pipeline import JudgeDeps
from sahujudge.sandbox import Sandbox

SECRET_INPUT = "HIDDEN-INPUT-SENTINEL-5d1c"
SECRET_ANSWER = "HIDDEN-ANSWER-SENTINEL-8e2f"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "test",
        "database_url": "sqlite+aiosqlite://",
        "redis_url": "redis://unused:6379/0",
        "jwt_secret": "test-secret-test-secret-test-secret-0123",
        "argon2_time_cost": 1,
        "argon2_memory_kib": 8,
        "argon2_parallelism": 1,
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(**values)


@dataclass
class World:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: Any
    deps: JudgeDeps
    _subscriptions: list[Any] = field(default_factory=list)

    async def close(self) -> None:
        for sub in self._subscriptions:
            await sub.aclose()
        await self.engine.dispose()

    async def add_user(self, username: str = "ada") -> uuid.UUID:
        async with self.sessionmaker() as db:
            user = await users.create_user(
                db, self.settings, email=f"{username}@example.com", username=username, password="correct-horse-battery"
            )
            await db.commit()
            return user.id

    async def add_problem(
        self,
        slug: str = "double",
        tests: tuple[tuple[str, str, str], ...] = (
            ("PUBLIC", "1\n", "2\n"),
            ("HIDDEN", "5\n", "10\n"),
            ("HIDDEN", "21\n", "42\n"),
        ),
        *,
        checker: str = "lines",
        time_limit_ms: int = 2000,
        memory_limit_mb: int = 128,
    ) -> uuid.UUID:
        async with self.sessionmaker() as db:
            problem = Problem(
                id=uuid.uuid4(),
                slug=slug,
                title=slug.title(),
                description="d" * 10,
                difficulty="EASY",
                constraints="c",
                input_format="i",
                output_format="o",
                time_limit_ms=time_limit_ms,
                memory_limit_mb=memory_limit_mb,
                checker=checker,
                published=True,
                published_at=utcnow(),
            )
            cases = [
                ProblemTestCase(id=uuid.uuid4(), kind=kind, position=n, input_data=inp, expected_output=out)
                for n, (kind, inp, out) in enumerate(tests)
            ]
            problem.test_cases = cases
            first_public = next((c for c in cases if c.kind == CaseKind.PUBLIC), None)
            if first_public:
                problem.examples = [ProblemExample(test_case=first_public, position=0)]
            db.add(problem)
            await db.commit()
            return problem.id

    async def add_submission(
        self, user_id: uuid.UUID, problem_id: uuid.UUID, source: str, *, language: str = "python", total: int = 3
    ) -> uuid.UUID:
        async with self.sessionmaker() as db:
            submission = Submission(
                user_id=user_id,
                problem_id=problem_id,
                language_key=language,
                source_code=source,
                status=SubmissionStatus.QUEUED.value,
                total_count=total,
            )
            db.add(submission)
            await db.commit()
            return submission.id

    async def subscribe(self, user_id: uuid.UUID) -> Any:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(events.user_channel(user_id))
        self._subscriptions.append(pubsub)
        return pubsub


async def drain(pubsub: Any, *, quiet_for: float = 0.15) -> list[dict[str, Any]]:
    """Every event received until the channel goes quiet (the first get_message eats the subscribe confirmation)."""
    seen: list[dict[str, Any]] = []
    loop = asyncio.get_running_loop()
    last = loop.time()
    while loop.time() - last < quiet_for:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.02)
        if message is not None:
            seen.append(json.loads(message["data"]))
            last = loop.time()
    return seen


async def new_world(sandbox: Sandbox, **settings_overrides: Any) -> World:
    settings = make_settings(**settings_overrides)
    engine = create_engine_from_settings(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = create_sessionmaker(engine)
    async with sessionmaker() as db:
        db.add_all(Role(name=r.value, description=r.value.title()) for r in RoleName)
        db.add_all(
            ProgrammingLanguage(key=key, display_name=key, editor_language=key, file_extension=ext)
            for key, ext in (("python", "py"), ("cpp", "cpp"), ("javascript", "js"), ("ruby", "rb"))
        )
        # Real rows, not a test-only stand-in: evaluate_achievements() inserts user_achievements rows referencing
        # these keys, and that foreign key IS enforced on PostgreSQL even though SQLite here won't catch a mismatch.
        db.add_all(
            Achievement(key=a.key, name=a.name, description=a.description, icon=a.icon, sort_order=a.sort_order)
            for a in ACHIEVEMENT_CATALOG
        )
        await db.commit()
    redis = fakeredis.FakeAsyncRedis(server=fakeredis.FakeServer(), decode_responses=True)
    deps = JudgeDeps(sessionmaker=sessionmaker, redis=redis, sandbox=sandbox, settings=settings)
    return World(settings=settings, engine=engine, sessionmaker=sessionmaker, redis=redis, deps=deps)
