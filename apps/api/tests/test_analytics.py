"""Admin analytics (phase 8): platform totals plus a read of the AiUsage rows recorded since phase 5."""

from __future__ import annotations

import pytest

from tests.conftest import FakeAiProvider, make_settings, signed_in
from tests.problems_helpers import admin_session, insert_problem

pytestmark = pytest.mark.anyio

CONFIGURED = {"ollama_model": "test-model"}


async def test_requires_admin_role(build_app) -> None:
    app = await build_app()
    async with signed_in(app, username="plain") as (client, headers):
        r = await client.get("/api/admin/analytics", headers=headers)
        assert r.status_code == 403


async def test_platform_totals_reflect_real_data(build_app) -> None:
    app = await build_app()
    await insert_problem(app, "two-sum")
    await insert_problem(app, "hidden-one", published=False)

    async with admin_session(app) as (admin, headers):
        r = await admin.get("/api/admin/analytics", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()

    assert body["platform"]["published_problems"] == 1
    assert body["platform"]["users"] >= 1  # at least the admin created by admin_session


async def test_ai_usage_summary_reflects_real_requests(build_app) -> None:
    """Two requests against the SAME app (one app == one database — see conftest's `build_app`, which drops and
    recreates every table on each call; two apps under TEST_DATABASE_URL would share, and stomp on, one Postgres
    database). One provider instance, its `down` flag flipped between requests, gives one success and one failure
    without needing a second app."""
    provider = FakeAiProvider(tokens=["ok"])
    app = await build_app(settings=make_settings(**CONFIGURED), ai_provider=provider)

    async with signed_in(app, username="ada") as (client, headers):
        await client.post("/api/ai/conversations", json={"message": "hi"}, headers=headers)

    async with signed_in(app, username="bob") as (client2, headers2):
        provider.down = True
        await client2.post("/api/ai/conversations", json={"message": "hi"}, headers=headers2)
        provider.down = False

    async with admin_session(app) as (admin, headers):
        r = await admin.get("/api/admin/analytics", headers=headers)
        assert r.status_code == 200, r.text
        usage = r.json()["ai_usage"]

    assert usage["total_requests"] == 2
    assert usage["failed_requests"] == 1
    chat = next(f for f in usage["by_feature"] if f["feature"] == "chat")
    assert chat["requests"] == 2 and chat["failed"] == 1


async def test_ai_usage_counts_failures_too(build_app) -> None:
    provider = FakeAiProvider(down=True)
    app = await build_app(settings=make_settings(**CONFIGURED), ai_provider=provider)

    async with signed_in(app, username="ada") as (client, headers):
        await client.post("/api/ai/conversations", json={"message": "hi"}, headers=headers)

    async with admin_session(app) as (admin, headers):
        r = await admin.get("/api/admin/analytics", headers=headers)
        usage = r.json()["ai_usage"]

    assert usage["total_requests"] == 1
    assert usage["failed_requests"] == 1
    chat = next(f for f in usage["by_feature"] if f["feature"] == "chat")
    assert chat["failed"] == 1
