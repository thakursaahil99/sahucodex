"""Client address resolution and Origin checks."""

from __future__ import annotations

from starlette.requests import Request
from starlette.types import Scope

from app.core.config import Settings


def client_ip_from_scope(scope: Scope, trusted_proxy_count: int) -> str:
    """Resolve the caller's IP.

    With N trusted proxies in front of us, each appends the address it saw to X-Forwarded-For,
    so the N-th entry from the right is the real client. Entries further left are attacker-controlled
    and are ignored, which stops X-Forwarded-For spoofing from evading rate limits.
    """
    peer = scope.get("client")
    peer_ip = peer[0] if peer else "unknown"
    if trusted_proxy_count <= 0:
        return peer_ip
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            hops = [part.strip() for part in value.decode("latin-1").split(",") if part.strip()]
            if len(hops) >= trusted_proxy_count:
                return hops[-trusted_proxy_count]
            break
    return peer_ip


def client_ip(request: Request) -> str:
    settings: Settings = request.app.state.settings
    return client_ip_from_scope(request.scope, settings.trusted_proxy_count)


def user_agent(request: Request) -> str | None:
    value = request.headers.get("user-agent")
    return value[:255] if value else None
