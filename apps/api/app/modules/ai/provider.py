"""The AI provider abstraction and its one implementation: Ollama — local, open-source, no API key ever required.

Nothing outside this module knows it is talking to Ollama specifically: `service.py` calls `generate()` /
`stream_chat()` against whatever `AiProvider` is configured. A second provider (still local/open-source-first — see
docs/ai.md) would be a new class here, never a rewrite of the callers.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings

Message = tuple[str, str]  # (role, content) — role is "user" or "assistant"


class AiUnavailableError(RuntimeError):
    """The provider could not be reached, timed out, or is not configured. Never papered over with a made-up reply —
    callers turn this into a 503, exactly like SahuJudge does for a sandbox failure."""


@dataclass(frozen=True)
class GenerateResult:
    text: str
    duration_ms: int


class AiProvider(Protocol):
    model: str

    async def generate(self, *, system: str, prompt: str, max_tokens: int, timeout_s: float) -> GenerateResult: ...

    def stream_chat(
        self, *, system: str, messages: list[Message], max_tokens: int, timeout_s: float
    ) -> AsyncIterator[str]: ...


class OllamaProvider:
    """Talks to a real, local Ollama server over its HTTP API. No response is ever invented — an unreachable server,
    a missing model, or a timeout always raises `AiUnavailableError` rather than returning placeholder text."""

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(self, *, system: str, prompt: str, max_tokens: int, timeout_s: float) -> GenerateResult:
        started = time.monotonic()
        payload = {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AiUnavailableError(f"Ollama generate failed: {type(exc).__name__}") from exc
        return GenerateResult(text=data.get("response", ""), duration_ms=int((time.monotonic() - started) * 1000))

    async def stream_chat(
        self, *, system: str, messages: list[Message], max_tokens: int, timeout_s: float
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}]
            + [{"role": role, "content": content} for role, content in messages],
            "stream": True,
            "options": {"num_predict": max_tokens},
        }
        try:
            async with (
                httpx.AsyncClient(timeout=timeout_s) as client,
                client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response,
            ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done"):
                        return
        except (httpx.HTTPError, ValueError) as exc:
            raise AiUnavailableError(f"Ollama chat failed: {type(exc).__name__}") from exc

    async def is_reachable(self, *, timeout_s: float = 3.0) -> bool:
        """Used by /ready — never by a request handler (that always attempts the real call and reports honestly)."""
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except httpx.HTTPError:
            return False


def build_ai_provider(settings: Settings) -> AiProvider:
    return OllamaProvider(settings.ollama_base_url, settings.ollama_model)
