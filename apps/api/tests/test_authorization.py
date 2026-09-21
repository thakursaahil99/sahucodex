"""Server-side RBAC and access-control tests. The frontend is never trusted to enforce any of this."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.modules.users.models import RoleName, User
from tests.conftest import create_user, make_client, signed_in


async def test_admin_api_rejects_anonymous_users(client: AsyncClient):
    response = await client.get("/api/admin/users")
    assert response.status_code == 401


@pytest.mark.parametrize("role", [RoleName.USER, RoleName.MODERATOR])
async def test_admin_api_rejects_non_admins(app, role):
    async with signed_in(app, username="member", roles=(role,)) as (client, headers):
        response = await client.get("/api/admin/users", headers=headers)
    assert response.status_code == 403
    assert response.json() == {
        "success": False,
        "error": {"code": "FORBIDDEN", "message": "You do not have permission to do that"},
    }


async def test_admin_can_list_users_with_pagination_and_search(app):
    for name in ("alice", "alan", "bob"):
        await create_user(app, email=f"{name}@example.com", username=name)
    async with signed_in(app, username="boss", roles=(RoleName.ADMIN, RoleName.USER)) as (client, headers):
        page = await client.get("/api/admin/users?limit=2&page=1", headers=headers)
        assert page.status_code == 200
        body = page.json()
        assert body["total"] == 4 and body["pages"] == 2 and len(body["items"]) == 2
        assert all("password" not in key for item in body["items"] for key in item)

        found = await client.get("/api/admin/users?q=al", headers=headers)
        assert {u["username"] for u in found.json()["items"]} == {"alice", "alan"}

        # LIKE wildcards in the query are matched literally, not as patterns.
        assert (await client.get("/api/admin/users?q=%25", headers=headers)).json()["total"] == 0

        assert (await client.get("/api/admin/users?limit=1000", headers=headers)).status_code == 422


async def test_role_changes_apply_immediately_because_tokens_carry_no_role(app):
    async with signed_in(app, username="temp", roles=(RoleName.ADMIN, RoleName.USER)) as (client, headers):
        assert (await client.get("/api/admin/users", headers=headers)).status_code == 200
        async with app.state.sessionmaker() as db:
            user = await db.scalar(select(User).where(User.username == "temp"))
            user.role_links = [link for link in user.role_links if link.role_name != "ADMIN"]
            await db.commit()
        assert (await client.get("/api/admin/users", headers=headers)).status_code == 403


async def test_user_cannot_escalate_privileges_through_profile_update(app):
    async with signed_in(app, username="mallory") as (client, headers):
        for payload in (
            {"roles": ["ADMIN"]},
            {"role": "ADMIN"},
            {"is_active": True},
            {"email": "root@example.com"},
            {"username": "admin"},
            {"email_verified": True},
        ):
            response = await client.patch("/api/users/me", json=payload, headers=headers)
            assert response.status_code == 422, payload
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        me = await client.get("/api/users/me", headers=headers)
        assert me.json()["roles"] == ["USER"]
        assert (await client.get("/api/admin/users", headers=headers)).status_code == 403


async def test_profile_update_persists_and_validates(app):
    async with signed_in(app, username="ada") as (client, headers):
        ok = await client.patch(
            "/api/users/me",
            headers=headers,
            json={
                "bio": "  I like graphs.  ",
                "country": "in",
                "website": "https://ada.dev",
                "github_url": "https://github.com/ada",
                "avatar_url": "https://avatars.example/ada.png",
            },
        )
        assert ok.status_code == 200
        profile = ok.json()["profile"]
        assert profile["bio"] == "I like graphs."
        assert profile["country"] == "IN"
        assert profile["avatar_url"] == "https://avatars.example/ada.png"

        # A partial update keeps everything the client did not mention.
        await client.patch("/api/users/me", headers=headers, json={"bio": "Updated"})
        again = (await client.get("/api/users/me", headers=headers)).json()["profile"]
        assert again["bio"] == "Updated" and again["website"] == "https://ada.dev"

        # Explicit null clears a field.
        await client.patch("/api/users/me", headers=headers, json={"website": None})
        assert (await client.get("/api/users/me", headers=headers)).json()["profile"]["website"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"website": "javascript:alert(1)"},
        {"website": "data:text/html,<script>alert(1)</script>"},
        {"website": "https://user:pass@example.com"},
        {"website": "ftp://example.com"},
        {"github_url": "https://evil.example/ada"},
        {"github_url": "https://github.com.evil.example/ada"},
        {"avatar_url": "javascript:alert(1)"},
        {"avatar_url": "data:image/svg+xml,<svg onload=alert(1)>"},
        {"country": "USA"},
        {"bio": "x" * 501},
    ],
)
async def test_profile_update_rejects_dangerous_or_malformed_values(app, payload):
    async with signed_in(app, username="ada") as (client, headers):
        assert (await client.patch("/api/users/me", json=payload, headers=headers)).status_code == 422


async def test_public_profile_hides_private_data(app):
    await create_user(app, email="secret@example.com", username="grace")
    async with make_client(app) as client:
        response = await client.get("/api/users/Grace")  # case-insensitive, no auth needed
        assert response.status_code == 200
        body = response.json()
        assert body["username"] == "grace"
        assert set(body) == {"username", "avatar_url", "bio", "country", "website", "github_url", "joined_at"}
        assert "secret@example.com" not in response.text

        missing = await client.get("/api/users/nobody")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "USER_NOT_FOUND"


async def test_deactivated_users_have_no_public_profile(app):
    await create_user(app, username="grace", email="grace@example.com")
    async with app.state.sessionmaker() as db:
        await db.execute(update(User).values(is_active=False))
        await db.commit()
    async with make_client(app) as client:
        assert (await client.get("/api/users/grace")).status_code == 404
