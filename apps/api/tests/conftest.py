"""Hermetic test setup: in-memory SQLite + fakeredis, no network, no containers."""

from __future__ import annotations

import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import fakeredis
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from qdrant_client import AsyncQdrantClient

import app.db_models
from app.core.config import Settings
from app.core.db import Base
from app.core.queue import QueueUnavailableError
from app.main import create_app
from app.modules.ai.provider import AiUnavailableError, GenerateResult
from app.modules.problems.models import ProgrammingLanguage
from app.modules.profiles.achievements import CATALOG as ACHIEVEMENT_CATALOG
from app.modules.profiles.models import Achievement
from app.modules.users import service as users
from app.modules.users.models import Role, RoleName

PASSWORD = "correct-horse-battery"

# Set TEST_DATABASE_URL (e.g. postgresql://user@localhost:5432/sahucodex_test) to run the whole suite
# against PostgreSQL instead of in-memory SQLite. The database is dropped and recreated per test.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "database_url": TEST_DATABASE_URL or "sqlite+aiosqlite://",
        "redis_url": "redis://unused:6379/0",
        "jwt_secret": "test-secret-test-secret-test-secret-0123",
        "argon2_time_cost": 1,
        "argon2_memory_kib": 8,
        "argon2_parallelism": 1,
        "cors_origins": "http://localhost:3000",
        "frontend_url": "http://localhost:3000",
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@dataclass
class Outbox:
    """Captures emails instead of sending them."""

    messages: list[dict[str, str]] = field(default_factory=list)

    async def send(self, to: str, subject: str, body: str) -> None:
        self.messages.append({"to": to, "subject": subject, "body": body})

    def last_token(self) -> str:
        match = re.search(r"token=([\w-]+)", self.messages[-1]["body"])
        assert match, "no token link in the last email"
        return match.group(1)


@dataclass
class RecordingQueue:
    """Stands in for Celery: records what would be enqueued, or simulates a broker outage."""

    jobs: list[tuple[str, tuple[str, ...], str]] = field(default_factory=list)
    down: bool = False

    async def enqueue(self, task: str, *args: str, queue: str) -> None:
        if self.down:
            raise QueueUnavailableError("broker is down")
        self.jobs.append((task, args, queue))


@dataclass
class FakeAiProvider:
    """Stands in for Ollama: returns scripted text and records exactly what it was sent, so tests can assert on the
    prompt (e.g. that a hidden test never reaches it). `down` simulates an unreachable server."""

    model: str = "test-model"
    reply: str = "Try thinking about the problem with two pointers."
    tokens: list[str] = field(default_factory=lambda: ["Hello", " ", "world"])
    down: bool = False
    generate_calls: list[dict[str, object]] = field(default_factory=list)
    chat_calls: list[dict[str, object]] = field(default_factory=list)

    async def generate(self, *, system: str, prompt: str, max_tokens: int, timeout_s: float) -> GenerateResult:
        self.generate_calls.append({"system": system, "prompt": prompt, "max_tokens": max_tokens})
        if self.down:
            raise AiUnavailableError("model server is down")
        return GenerateResult(text=self.reply, duration_ms=5)

    async def stream_chat(
        self, *, system: str, messages: list[tuple[str, str]], max_tokens: int, timeout_s: float
    ) -> AsyncIterator[str]:
        self.chat_calls.append({"system": system, "messages": list(messages), "max_tokens": max_tokens})
        if self.down:
            raise AiUnavailableError("model server is down")
        for token in self.tokens:
            yield token


@dataclass
class FakeEmbeddingProvider:
    """Deterministic stand-in for Ollama's /api/embeddings: maps each *lowercased substring* key in `vectors` to a
    fixed vector, so a test can control exactly which text embeds "near" which other text without a real model.
    Text matching no key falls back to `default_vector` (orthogonal to every real key by construction below)."""

    vectors: dict[str, list[float]] = field(default_factory=dict)
    # 768 dims to match the RAG collection's fixed size (see app.modules.rag.service._VECTOR_SIZE) — the last
    # component is set so this default is never the zero vector (Qdrant's cosine distance is undefined for that).
    default_vector: list[float] = field(default_factory=lambda: [0.0] * 767 + [1.0])
    down: bool = False
    embed_calls: list[str] = field(default_factory=list)

    async def embed(self, *, model: str, text: str, timeout_s: float) -> list[float]:
        self.embed_calls.append(text)
        if self.down:
            raise AiUnavailableError("embedding server is down")
        lowered = text.lower()
        for key, vector in self.vectors.items():
            if key.lower() in lowered:
                return vector
        return self.default_vector


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def outbox() -> Outbox:
    return Outbox()


AppFactory = Callable[..., Awaitable[FastAPI]]


@pytest_asyncio.fixture
async def build_app(outbox: Outbox) -> AsyncIterator[AppFactory]:
    """Factory so a test can build an app with custom settings."""
    created: list[FastAPI] = []

    async def factory(
        settings: Settings | None = None,
        redis: object | None = None,
        queue: RecordingQueue | None = None,
        ai_provider: FakeAiProvider | None = None,
        embedding_provider: object | None = None,
        qdrant_client: object | None = None,
    ) -> FastAPI:
        redis = redis or fakeredis.FakeAsyncRedis(server=fakeredis.FakeServer(), decode_responses=True)
        app = create_app(
            settings or make_settings(),
            redis_client=redis,  # type: ignore[arg-type]
            email_sender=outbox,
            job_queue=queue or RecordingQueue(),
            ai_provider=ai_provider or FakeAiProvider(),
            # An in-process Qdrant, never a real network client — `rag_configured` is False by default
            # (make_settings leaves QDRANT_URL unset) so nothing here is ever queried, but building a real
            # AsyncQdrantClient against an unreachable localhost:6333 still costs a connection attempt (and a
            # noisy warning) per test.
            qdrant_client=qdrant_client or AsyncQdrantClient(location=":memory:"),  # type: ignore[arg-type]
        )
        if embedding_provider is not None:
            app.state.embedding_provider = embedding_provider
        async with app.state.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        async with app.state.sessionmaker() as db:
            db.add_all(Role(name=r.value, description=r.value.title()) for r in RoleName)
            db.add_all(
                ProgrammingLanguage(
                    key=key, display_name=name, editor_language=key, file_extension=ext, sort_order=order
                )
                for order, (key, name, ext) in enumerate(
                    [
                        ("python", "Python 3", "py"),
                        ("cpp", "C++17", "cpp"),
                        ("javascript", "JavaScript (Node.js)", "js"),
                        ("c", "C17", "c"),
                        ("java", "Java 21", "java"),
                        ("csharp", "C# 12", "cs"),
                        ("go", "Go 1.23", "go"),
                        ("rust", "Rust (stable)", "rs"),
                        ("typescript", "TypeScript", "ts"),
                        ("php", "PHP 8", "php"),
                    ]
                )
            )
            db.add_all(
                Achievement(key=a.key, name=a.name, description=a.description, icon=a.icon, sort_order=a.sort_order)
                for a in ACHIEVEMENT_CATALOG
            )
            await db.commit()
        created.append(app)
        return app

    yield factory
    for app in created:
        await app.state.engine.dispose()


@pytest_asyncio.fixture
async def app(build_app: AppFactory) -> FastAPI:
    return await build_app()


def make_client(app: FastAPI, **kwargs: object) -> AsyncClient:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://localhost", **kwargs)  # type: ignore[arg-type]


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with make_client(app) as c:
        yield c


async def create_user(
    app: FastAPI,
    *,
    email: str = "ada@example.com",
    username: str = "ada",
    password: str = PASSWORD,
    roles: tuple[RoleName, ...] = (RoleName.USER,),
) -> None:
    async with app.state.sessionmaker() as db:
        await users.create_user(db, app.state.settings, email=email, username=username, password=password, roles=roles)
        await db.commit()


async def login(client: AsyncClient, identifier: str = "ada@example.com", password: str = PASSWORD) -> dict:
    response = await client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@asynccontextmanager
async def signed_in(app: FastAPI, *, username: str, roles: tuple[RoleName, ...] = (RoleName.USER,)):
    """Creates a user, signs them in, and yields (client, auth_headers)."""
    await create_user(app, email=f"{username}@example.com", username=username, roles=roles)
    async with make_client(app) as client:
        tokens = await login(client, f"{username}@example.com")
        yield client, bearer(tokens["access_token"])
