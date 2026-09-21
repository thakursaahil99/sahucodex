from __future__ import annotations

from datetime import timedelta

import jwt
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.db import utcnow
from app.core.security import create_access_token
from app.modules.auth.models import OneTimeToken, RefreshToken
from app.modules.users.models import User
from tests.conftest import PASSWORD, bearer, create_user, login, make_client, make_settings

REGISTER = {"email": "ada@example.com", "username": "Ada", "password": PASSWORD}


# --- Registration ----------------------------------------------------------------------------


async def test_register_creates_user_without_leaking_secrets(client: AsyncClient, app):
    response = await client.post("/api/auth/register", json=REGISTER)
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["username"] == "Ada"
    assert body["user"]["roles"] == ["USER"]
    assert "password" not in response.text.lower()  # neither the password nor its hash is ever returned

    async with app.state.sessionmaker() as db:
        stored = await db.scalar(select(User))
        assert stored.password_hash.startswith("$argon2id$")
        assert PASSWORD not in stored.password_hash


async def test_register_rejects_duplicates_case_insensitively(client: AsyncClient):
    assert (await client.post("/api/auth/register", json=REGISTER)).status_code == 201

    same_email = await client.post(
        "/api/auth/register", json={**REGISTER, "email": "ADA@example.com", "username": "other"}
    )
    assert same_email.status_code == 409
    assert same_email.json()["error"]["code"] == "EMAIL_TAKEN"

    same_username = await client.post(
        "/api/auth/register", json={**REGISTER, "email": "x@example.com", "username": "ADA"}
    )
    assert same_username.status_code == 409
    assert same_username.json()["error"]["code"] == "USERNAME_TAKEN"


async def test_register_validates_input(client: AsyncClient):
    weak_password = "Zq7-pwd!"
    weak = await client.post("/api/auth/register", json={**REGISTER, "password": weak_password})
    assert weak.status_code == 422
    assert weak.json()["success"] is False
    assert weak.json()["error"]["code"] == "VALIDATION_ERROR"
    # The submitted password must never be echoed back in validation details.
    assert weak_password not in weak.text

    assert (await client.post("/api/auth/register", json={**REGISTER, "username": "bad name!"})).status_code == 422
    assert (await client.post("/api/auth/register", json={**REGISTER, "email": "not-an-email"})).status_code == 422
    reserved = await client.post("/api/auth/register", json={**REGISTER, "username": "Admin"})
    assert reserved.status_code == 409


async def test_register_ignores_client_supplied_roles(client: AsyncClient, app):
    response = await client.post("/api/auth/register", json={**REGISTER, "roles": ["ADMIN"], "is_active": False})
    assert response.status_code == 201
    assert response.json()["user"]["roles"] == ["USER"]


async def test_register_sends_verification_email(client: AsyncClient, outbox):
    await client.post("/api/auth/register", json=REGISTER)
    assert len(outbox.messages) == 1
    assert outbox.messages[0]["to"] == "ada@example.com"
    assert "/verify-email?token=" in outbox.messages[0]["body"]


# --- Login -----------------------------------------------------------------------------------


async def test_login_by_email_and_username(client: AsyncClient, app):
    await create_user(app)
    by_email = await login(client, "ada@example.com")
    by_username = await login(client, "ADA")
    assert by_email["token_type"] == "bearer"
    assert by_email["expires_in"] == 900
    assert by_username["user"]["username"] == "ada"


async def test_login_sets_httponly_scoped_refresh_cookie_and_keeps_token_out_of_body(client: AsyncClient, app):
    await create_user(app)
    response = await client.post("/api/auth/login", json={"identifier": "ada", "password": PASSWORD})
    cookies = response.headers.get_list("set-cookie")
    refresh_cookie = next(c for c in cookies if c.startswith("sahucodex_refresh="))
    assert "HttpOnly" in refresh_cookie
    assert "Path=/api/auth" in refresh_cookie
    assert "SameSite=lax" in refresh_cookie
    hint_cookie = next(c for c in cookies if c.startswith("sahucodex_session="))
    assert "HttpOnly" not in hint_cookie
    assert client.cookies.get("sahucodex_refresh") not in response.text


async def test_login_failure_is_uniform_and_generic(client: AsyncClient, app):
    await create_user(app)
    wrong_password = await client.post("/api/auth/login", json={"identifier": "ada", "password": "nope-nope-nope"})
    unknown_user = await client.post("/api/auth/login", json={"identifier": "ghost", "password": "nope-nope-nope"})
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_disabled_account_cannot_login(client: AsyncClient, app):
    await create_user(app)
    async with app.state.sessionmaker() as db:
        await db.execute(update(User).values(is_active=False))
        await db.commit()
    response = await client.post("/api/auth/login", json={"identifier": "ada", "password": PASSWORD})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCOUNT_DISABLED"


async def test_login_is_rate_limited_per_ip(client: AsyncClient, app):
    await create_user(app)
    statuses = []
    for _ in range(7):
        r = await client.post("/api/auth/login", json={"identifier": "ada", "password": "wrong-wrong-wrong"})
        statuses.append(r.status_code)
    assert statuses[:5] == [401] * 5
    assert statuses[5:] == [429, 429]
    assert r.headers["retry-after"].isdigit()
    assert r.json()["error"]["code"] == "RATE_LIMITED"


async def test_rate_limiting_can_be_disabled(build_app, app):
    disabled = await build_app(make_settings(rate_limit_enabled=False))
    await create_user(disabled)
    async with make_client(disabled) as c:
        for _ in range(8):
            r = await c.post("/api/auth/login", json={"identifier": "ada", "password": "wrong-wrong-wrong"})
            assert r.status_code == 401


# --- Access tokens ---------------------------------------------------------------------------


async def test_protected_route_requires_a_valid_token(client: AsyncClient, app):
    await create_user(app)
    missing = await client.get("/api/users/me")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "NOT_AUTHENTICATED"
    assert missing.headers["www-authenticate"] == "Bearer"

    garbage = await client.get("/api/users/me", headers=bearer("not.a.jwt"))
    assert garbage.json()["error"]["code"] == "TOKEN_INVALID"

    tokens = await login(client)
    ok = await client.get("/api/users/me", headers=bearer(tokens["access_token"]))
    assert ok.status_code == 200
    assert ok.json()["email"] == "ada@example.com"


async def test_expired_token_is_reported_distinctly(client: AsyncClient, app):
    await create_user(app)
    tokens = await login(client)
    user_id = tokens["user"]["id"]
    import uuid

    expired, _ = create_access_token(uuid.UUID(user_id), uuid.uuid4(), make_settings(jwt_access_expire=-30))
    response = await client.get("/api/users/me", headers=bearer(expired))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"


async def test_token_signed_with_another_secret_or_alg_none_is_rejected(client: AsyncClient, app):
    await create_user(app)
    tokens = await login(client)
    claims = jwt.decode(tokens["access_token"], options={"verify_signature": False})

    forged = jwt.encode(claims, "an-attacker-chosen-secret-of-32-chars!", algorithm="HS256")
    assert (await client.get("/api/users/me", headers=bearer(forged))).json()["error"]["code"] == "TOKEN_INVALID"

    unsigned = jwt.encode(claims, key=None, algorithm="none")
    assert (await client.get("/api/users/me", headers=bearer(unsigned))).json()["error"]["code"] == "TOKEN_INVALID"


async def test_token_for_deleted_or_disabled_user_stops_working_immediately(client: AsyncClient, app):
    await create_user(app)
    tokens = await login(client)
    async with app.state.sessionmaker() as db:
        await db.execute(update(User).values(is_active=False))
        await db.commit()
    response = await client.get("/api/users/me", headers=bearer(tokens["access_token"]))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ACCOUNT_UNAVAILABLE"


# --- Refresh rotation ------------------------------------------------------------------------


async def test_refresh_rotates_the_refresh_token(client: AsyncClient, app):
    await create_user(app)
    first = await login(client)
    old_refresh = client.cookies.get("sahucodex_refresh")

    response = await client.post("/api/auth/refresh")
    assert response.status_code == 200
    new_refresh = client.cookies.get("sahucodex_refresh")
    assert new_refresh and new_refresh != old_refresh
    assert response.json()["access_token"] != first["access_token"]

    async with app.state.sessionmaker() as db:
        rows = list(await db.scalars(select(RefreshToken).order_by(RefreshToken.created_at)))
    assert len(rows) == 2
    assert rows[0].revoked_reason == "ROTATED"
    assert rows[0].family_id == rows[1].family_id
    assert rows[1].revoked_at is None
    # Only hashes are stored.
    assert old_refresh not in {r.token_hash for r in rows}


async def test_refresh_without_cookie_is_401_and_clears_hint_cookie(client: AsyncClient):
    response = await client.post("/api/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "REFRESH_TOKEN_MISSING"
    assert any(c.startswith("sahucodex_session=") and "Max-Age=0" in c for c in response.headers.get_list("set-cookie"))


async def test_replaying_a_rotated_token_after_grace_revokes_the_whole_session(client: AsyncClient, app):
    await create_user(app)
    await login(client)
    stolen = client.cookies.get("sahucodex_refresh")
    assert (await client.post("/api/auth/refresh")).status_code == 200
    legit_current = client.cookies.get("sahucodex_refresh")

    # Pretend the rotation happened a minute ago (outside the race-tolerance window).
    async with app.state.sessionmaker() as db:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.revoked_reason == "ROTATED")
            .values(revoked_at=utcnow() - timedelta(minutes=1))
        )
        await db.commit()

    async with make_client(app) as attacker:
        attacker.cookies.set("sahucodex_refresh", stolen, path="/api/auth")
        replay = await attacker.post("/api/auth/refresh")
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "REFRESH_TOKEN_REUSED"

    # The legitimate holder's newest token is now dead too: the family was revoked.
    client.cookies.set("sahucodex_refresh", legit_current, path="/api/auth")
    after = await client.post("/api/auth/refresh")
    assert after.status_code == 401

    async with app.state.sessionmaker() as db:
        assert await db.scalar(select(RefreshToken).where(RefreshToken.revoked_reason == "REUSE_DETECTED")) is not None


async def test_immediate_reuse_is_treated_as_a_benign_race_not_theft(client: AsyncClient, app):
    await create_user(app)
    await login(client)
    first_cookie = client.cookies.get("sahucodex_refresh")
    assert (await client.post("/api/auth/refresh")).status_code == 200
    newest = client.cookies.get("sahucodex_refresh")

    async with make_client(app) as other_tab:
        other_tab.cookies.set("sahucodex_refresh", first_cookie, path="/api/auth")
        raced = await other_tab.post("/api/auth/refresh")
    assert raced.status_code == 401
    assert raced.json()["error"]["code"] == "REFRESH_TOKEN_RACE"
    assert not raced.headers.get_list("set-cookie")  # must not clear anything

    # The session survives: the newest token still works.
    client.cookies.set("sahucodex_refresh", newest, path="/api/auth")
    assert (await client.post("/api/auth/refresh")).status_code == 200


async def test_expired_refresh_token_is_rejected(client: AsyncClient, app):
    await create_user(app)
    await login(client)
    async with app.state.sessionmaker() as db:
        await db.execute(update(RefreshToken).values(expires_at=utcnow() - timedelta(seconds=1)))
        await db.commit()
    response = await client.post("/api/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "REFRESH_TOKEN_EXPIRED"


async def test_refresh_rejects_cross_site_origin(client: AsyncClient, app):
    await create_user(app)
    await login(client)
    forged = await client.post("/api/auth/refresh", headers={"Origin": "https://evil.example"})
    assert forged.status_code == 403
    assert forged.json()["error"]["code"] == "CSRF_ORIGIN_MISMATCH"
    allowed = await client.post("/api/auth/refresh", headers={"Origin": "http://localhost:3000"})
    assert allowed.status_code == 200


# --- Logout & sessions -----------------------------------------------------------------------


async def test_logout_revokes_session_and_invalidates_access_token_immediately(client: AsyncClient, app):
    await create_user(app)
    tokens = await login(client)
    headers = bearer(tokens["access_token"])
    assert (await client.get("/api/users/me", headers=headers)).status_code == 200
    refresh_cookie = client.cookies.get("sahucodex_refresh")

    out = await client.post("/api/auth/logout")
    assert out.status_code == 204
    assert any("Max-Age=0" in c for c in out.headers.get_list("set-cookie"))

    revoked = await client.get("/api/users/me", headers=headers)
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "TOKEN_REVOKED"

    client.cookies.set("sahucodex_refresh", refresh_cookie, path="/api/auth")
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_logout_is_idempotent(client: AsyncClient):
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.post("/api/auth/logout")).status_code == 204


async def test_sessions_can_be_listed_and_revoked(client: AsyncClient, app):
    await create_user(app)
    first = await login(client)
    async with make_client(app) as second_device:
        second = await login(second_device)

    listing = await client.get("/api/auth/sessions", headers=bearer(first["access_token"]))
    sessions = listing.json()
    assert len(sessions) == 2
    assert sum(s["current"] for s in sessions) == 1

    other = next(s for s in sessions if not s["current"])
    assert (
        await client.delete(f"/api/auth/sessions/{other['id']}", headers=bearer(first["access_token"]))
    ).status_code == 204
    # The revoked device's access token dies immediately.
    assert (await client.get("/api/users/me", headers=bearer(second["access_token"]))).status_code == 401
    assert len((await client.get("/api/auth/sessions", headers=bearer(first["access_token"]))).json()) == 1


async def test_user_cannot_revoke_someone_elses_session(client: AsyncClient, app):
    await create_user(app)
    await create_user(app, email="bob@example.com", username="bob")
    ada = await login(client)
    async with make_client(app) as bob_client:
        bob = await login(bob_client, "bob@example.com")
        bob_session = (await bob_client.get("/api/auth/sessions", headers=bearer(bob["access_token"]))).json()[0]

    response = await client.delete(f"/api/auth/sessions/{bob_session['id']}", headers=bearer(ada["access_token"]))
    assert response.status_code == 404
    assert (await client.get("/api/users/me", headers=bearer(bob["access_token"]))).status_code == 200


# --- Password reset --------------------------------------------------------------------------


async def test_password_reset_flow(client: AsyncClient, app, outbox):
    await create_user(app)
    tokens = await login(client)

    forgot = await client.post("/api/auth/password/forgot", json={"email": "ada@example.com"})
    assert forgot.status_code == 202
    token = outbox.last_token()
    assert outbox.messages[-1]["to"] == "ada@example.com"

    new_password = "an-entirely-new-passphrase"
    reset = await client.post("/api/auth/password/reset", json={"token": token, "new_password": new_password})
    assert reset.status_code == 200

    # Old sessions are killed, old password is dead, new one works.
    assert (await client.get("/api/users/me", headers=bearer(tokens["access_token"]))).status_code == 401
    bad = await client.post("/api/auth/login", json={"identifier": "ada", "password": PASSWORD})
    assert bad.status_code == 401
    assert (
        await client.post("/api/auth/login", json={"identifier": "ada", "password": new_password})
    ).status_code == 200

    # Single use.
    again = await client.post(
        "/api/auth/password/reset", json={"token": token, "new_password": "yet-another-passphrase"}
    )
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "TOKEN_INVALID"


async def test_forgot_password_does_not_reveal_whether_an_email_exists(client: AsyncClient, app, outbox):
    await create_user(app)
    known = await client.post("/api/auth/password/forgot", json={"email": "ada@example.com"})
    unknown = await client.post("/api/auth/password/forgot", json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert [m["to"] for m in outbox.messages] == ["ada@example.com"]


async def test_expired_or_forged_reset_tokens_are_rejected(client: AsyncClient, app, outbox):
    await create_user(app)
    await client.post("/api/auth/password/forgot", json={"email": "ada@example.com"})
    token = outbox.last_token()
    async with app.state.sessionmaker() as db:
        await db.execute(update(OneTimeToken).values(expires_at=utcnow() - timedelta(seconds=1)))
        await db.commit()
    body = {"token": token, "new_password": "brand-new-passphrase"}
    assert (await client.post("/api/auth/password/reset", json=body)).status_code == 400
    forged = {"token": "x" * 43, "new_password": "brand-new-passphrase"}
    assert (await client.post("/api/auth/password/reset", json=forged)).status_code == 400


async def test_a_newer_reset_link_invalidates_the_older_one(client: AsyncClient, app, outbox):
    await create_user(app)
    await client.post("/api/auth/password/forgot", json={"email": "ada@example.com"})
    older = outbox.last_token()
    await client.post("/api/auth/password/forgot", json={"email": "ada@example.com"})
    newer = outbox.last_token()
    assert older != newer
    body = {"new_password": "brand-new-passphrase"}
    assert (await client.post("/api/auth/password/reset", json={"token": older, **body})).status_code == 400
    assert (await client.post("/api/auth/password/reset", json={"token": newer, **body})).status_code == 200


# --- Email verification ----------------------------------------------------------------------


async def test_email_verification_flow(client: AsyncClient, app, outbox):
    await client.post("/api/auth/register", json=REGISTER)
    token = outbox.last_token()
    tokens = await login(client)
    assert tokens["user"]["email_verified"] is False

    assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 200
    me = await client.get("/api/users/me", headers=bearer(tokens["access_token"]))
    assert me.json()["email_verified"] is True

    reuse = await client.post("/api/auth/verify-email", json={"token": token})
    assert reuse.status_code == 400


async def test_a_password_reset_token_cannot_verify_an_email(client: AsyncClient, app, outbox):
    await create_user(app)
    await client.post("/api/auth/password/forgot", json={"email": "ada@example.com"})
    token = outbox.last_token()
    assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 400


async def test_username_uniqueness_is_enforced_by_the_database_not_just_the_service(app):
    import pytest
    from sqlalchemy.exc import IntegrityError

    await create_user(app, email="a@example.com", username="Ada")
    with pytest.raises(IntegrityError):
        await create_user(app, email="b@example.com", username="ada")
