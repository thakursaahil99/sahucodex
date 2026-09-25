"""Qdrant wiring: one client per app, built once at startup exactly like `AiProvider` — never per-request.

Optional by construction (see `Settings.rag_configured`): with no `QDRANT_URL` set, a client is still built (its
constructor does not connect), but nothing in this module is ever called — `app.modules.rag.service` checks
`rag_configured` before touching it. A Qdrant that is configured but unreachable behaves like Ollama unreachable:
`RagUnavailableError`, surfaced as a clean failure, never a fake or empty-looking result standing in for a real one.
"""

from __future__ import annotations

from qdrant_client import AsyncQdrantClient

from app.core.config import Settings


class RagUnavailableError(RuntimeError):
    """Qdrant is not configured, or a configured Qdrant could not be reached."""


def build_qdrant_client(settings: Settings) -> AsyncQdrantClient:
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    return AsyncQdrantClient(url=settings.qdrant_url or "http://localhost:6333", api_key=api_key, timeout=10)
