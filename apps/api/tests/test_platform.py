"""Health, metrics, headers, error envelope, request limits, CORS."""

from __future__ import annotations

import fakeredis
from httpx import AsyncClient

from tests.conftest import make_client, make_settings

# --- Health / readiness / metrics ------------------------------------------------------------


async def test_health_is_up(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_reports_dependencies(client: AsyncClient):
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok", "redis": "ok"}}


async def test_ready_returns_503_without_leaking_internals_when_redis_is_down(build_app):
    class DeadRedis(fakeredis.FakeAsyncRedis):
        async def ping(self, *args, **kwargs):
            raise ConnectionError("connect to redis://secret-host:6379 failed: password=hunter2")

    app = await build_app(redis=DeadRedis(server=fakeredis.FakeServer(), decode_responses=True))
    async with make_client(app) as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"database": "ok", "redis": "unavailable"}}
    assert "secret-host" not in response.text and "hunter2" not in response.text


async def test_metrics_expose_request_counters_by_route_template(client: AsyncClient):
    await client.get("/api/users/someone")  # 404, but the route template must still be recorded
    body = (await client.get("/metrics")).text
    assert "sahucodex_http_requests_total" in body
    assert 'route="/api/users/{username}"' in body
    assert "sahucodex_http_request_duration_seconds_bucket" in body


async def test_metrics_require_token_when_configured(build_app):
    app = await build_app(make_settings(metrics_token="scrape-token-scrape-token"))
    async with make_client(app) as client:
        assert (await client.get("/metrics")).status_code == 401
        assert (await client.get("/metrics", headers={"Authorization": "Bearer wrong"})).status_code == 401
        ok = await client.get("/metrics", headers={"Authorization": "Bearer scrape-token-scrape-token"})
        assert ok.status_code == 200


# --- Error envelope --------------------------------------------------------------------------


async def test_unknown_routes_and_methods_use_the_error_envelope(client: AsyncClient):
    missing = await client.get("/api/nope")
    assert missing.status_code == 404
    assert missing.json()["success"] is False and missing.json()["error"]["code"] == "NOT_FOUND"

    wrong_method = await client.delete("/api/auth/login")
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


async def test_unhandled_errors_do_not_expose_stack_traces(app):
    async def boom() -> None:
        raise RuntimeError("database password is hunter2 at /srv/app/secret.py")

    app.add_api_route("/api/boom", boom)
    async with make_client(app) as client:
        response = await client.get("/api/boom")
    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
    }
    assert "hunter2" not in response.text and "Traceback" not in response.text


# --- Headers, request ids, limits, CORS ------------------------------------------------------


async def test_security_headers_are_set(client: AsyncClient):
    headers = (await client.get("/health")).headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert "strict-transport-security" not in headers  # HSTS is production-only

    auth_headers = (await client.post("/api/auth/logout")).headers
    assert auth_headers["cache-control"] == "no-store"


async def test_hsts_is_enabled_in_production(build_app):
    app = await build_app(
        make_settings(
            app_env="production",
            jwt_secret="a-genuinely-random-production-secret-value",
            email_backend="smtp",
        )
    )
    async with make_client(app) as client:
        assert "max-age=" in (await client.get("/health")).headers["strict-transport-security"]


async def test_docs_get_a_csp_that_lets_swagger_load(client: AsyncClient):
    response = await client.get("/api/docs")
    assert response.status_code == 200
    assert "cdn.jsdelivr.net" in response.headers["content-security-policy"]
    assert (await client.get("/api/openapi.json")).status_code == 200


async def test_request_id_is_generated_and_safe_ids_are_echoed(client: AsyncClient):
    generated = (await client.get("/health")).headers["x-request-id"]
    assert len(generated) >= 8
    echoed = await client.get("/health", headers={"X-Request-ID": "trace-abc-12345"})
    assert echoed.headers["x-request-id"] == "trace-abc-12345"
    hostile = await client.get("/health", headers={"X-Request-ID": "bad id\twith spaces & <script>"})
    assert hostile.headers["x-request-id"] != "bad id\twith spaces & <script>"


async def test_oversized_bodies_are_rejected(build_app):
    app = await build_app(make_settings(max_request_bytes=1024))
    async with make_client(app) as client:
        declared = await client.post(
            "/api/auth/login", content=b"x" * 5000, headers={"Content-Type": "application/json"}
        )
        assert declared.status_code == 413
        assert declared.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"

        async def chunks():  # no Content-Length: the streamed size is what counts
            for _ in range(10):
                yield b"x" * 500

        streamed = await client.post("/api/auth/login", content=chunks(), headers={"Content-Type": "application/json"})
        assert streamed.status_code == 413


async def test_cors_only_allows_configured_origins(client: AsyncClient):
    allowed = await client.options(
        "/api/auth/login",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert allowed.headers["access-control-allow-credentials"] == "true"

    denied = await client.options(
        "/api/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in denied.headers
