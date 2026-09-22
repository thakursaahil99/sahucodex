"""The AI provider abstraction. Ollama (local, open-source, no API key) is the default; `OpenRouterProvider` is a
hosted fallback for deployments with no machine to run Ollama on, gated behind AI_PROVIDER=openrouter and its own key.

Nothing outside this module knows which provider is configured: `service.py` calls `generate()` / `stream_chat()`
against whatever `AiProvider` `build_ai_provider` returns. A further provider would be a new class here, never a
rewrite of the callers.
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


class OpenRouterProvider:
    """Talks to OpenRouter's OpenAI-compatible chat-completions API. Same no-fabrication contract as Ollama: any
    failure raises `AiUnavailableError` rather than returning placeholder text. The API key never appears in a log
    line, an error message, or a response — only in the Authorization header sent to OpenRouter itself."""

    def __init__(self, base_url: str, model: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key
        # Overridable so tests can point at an httpx.MockTransport instead of the real network.
        self._client_factory = lambda timeout_s: httpx.AsyncClient(timeout=timeout_s)

    def _headers(self) -> dict[str, str]:
        # HTTP-Referer/X-Title are OpenRouter's own convention for attributing traffic; harmless to omit but nice
        # to send. Neither carries anything private.
        return {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": "https://sahucodex.vercel.app",
            "X-Title": "SahuCodeX",
        }

    async def generate(self, *, system: str, prompt: str, max_tokens: int, timeout_s: float) -> GenerateResult:
        started = time.monotonic()
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            async with self._client_factory(timeout_s) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", json=payload, headers=self._headers()
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AiUnavailableError(f"OpenRouter generate failed: {type(exc).__name__}") from exc
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise AiUnavailableError("OpenRouter returned an unexpected response shape") from exc
        return GenerateResult(text=text, duration_ms=int((time.monotonic() - started) * 1000))

    async def stream_chat(
        self, *, system: str, messages: list[Message], max_tokens: int, timeout_s: float
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}]
            + [{"role": role, "content": content} for role, content in messages],
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            async with (
                self._client_factory(timeout_s) as client,
                client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload, headers=self._headers()
                ) as response,
            ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[len("data: ") :]
                    if data == "[DONE]":
                        return
                    chunk = json.loads(data)
                    # A trailing usage-only chunk (or any chunk with nothing new) may carry an empty `choices` list.
                    choices = chunk.get("choices") or []
                    delta = choices[0].get("delta", {}) if choices else {}
                    content = delta.get("content") or ""
                    if content:
                        yield content
        except (httpx.HTTPError, ValueError) as exc:
            raise AiUnavailableError(f"OpenRouter chat failed: {type(exc).__name__}") from exc

    async def is_reachable(self, *, timeout_s: float = 3.0) -> bool:
        """Used by /ready. A models listing costs nothing and needs no key, so a bad/missing key still shows the
        provider itself as reachable — `ai_configured` (key + model both set) is what gates the feature."""
        try:
            async with self._client_factory(timeout_s) as client:
                response = await client.get(f"{self.base_url}/models")
                return response.status_code == 200
        except httpx.HTTPError:
            return False


def build_ai_provider(settings: Settings) -> AiProvider:
    if settings.ai_provider == "openrouter":
        key = settings.openrouter_api_key.get_secret_value() if settings.openrouter_api_key else ""
        return OpenRouterProvider(settings.openrouter_base_url, settings.openrouter_model, key)
    return OllamaProvider(settings.ollama_base_url, settings.ollama_model)
