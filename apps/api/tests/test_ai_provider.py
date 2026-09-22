"""Provider-selection and OpenRouter wire-format tests — no network, no real Ollama/OpenRouter (that's
test_ai_live.py's job). httpx.MockTransport stands in for the real HTTP endpoint."""

from __future__ import annotations

import json

import httpx
import pytest

from app.modules.ai.provider import AiUnavailableError, OllamaProvider, OpenRouterProvider, build_ai_provider
from tests.conftest import make_settings


def test_build_ai_provider_defaults_to_ollama() -> None:
    provider = build_ai_provider(make_settings(ollama_model="qwen2.5:3b"))
    assert isinstance(provider, OllamaProvider)
    assert provider.model == "qwen2.5:3b"


def test_build_ai_provider_selects_openrouter() -> None:
    provider = build_ai_provider(
        make_settings(ai_provider="openrouter", openrouter_model="meta-llama/llama-3.1-8b-instruct:free")
    )
    assert isinstance(provider, OpenRouterProvider)
    assert provider.model == "meta-llama/llama-3.1-8b-instruct:free"


def test_ai_configured_requires_both_key_and_model_for_openrouter() -> None:
    assert not make_settings(ai_provider="openrouter", openrouter_model="m").ai_configured
    assert not make_settings(ai_provider="openrouter", openrouter_api_key="k").ai_configured
    assert make_settings(ai_provider="openrouter", openrouter_model="m", openrouter_api_key="k").ai_configured


def _provider(handler) -> OpenRouterProvider:  # type: ignore[no-untyped-def]
    provider = OpenRouterProvider("https://openrouter.ai/api/v1", "some/model", "sk-test-key")
    transport = httpx.MockTransport(handler)
    provider._client_factory = lambda timeout_s: httpx.AsyncClient(transport=transport, timeout=timeout_s)  # type: ignore[attr-defined]
    return provider


async def test_generate_sends_the_key_and_parses_the_reply() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hint text"}}]})

    provider = _provider(handler)
    result = await provider.generate(system="sys", prompt="help", max_tokens=100, timeout_s=5)

    assert result.text == "hint text"
    assert seen["auth"] == "Bearer sk-test-key"
    body = seen["body"]
    assert body["model"] == "some/model"
    assert body["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "help"}]
    assert body["stream"] is False


async def test_generate_raises_on_http_error_never_returns_placeholder_text() -> None:
    provider = _provider(lambda request: httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(AiUnavailableError):
        await provider.generate(system="s", prompt="p", max_tokens=10, timeout_s=5)


async def test_generate_raises_on_an_unexpected_response_shape() -> None:
    provider = _provider(lambda request: httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(AiUnavailableError):
        await provider.generate(system="s", prompt="p", max_tokens=10, timeout_s=5)


async def test_stream_chat_yields_deltas_and_stops_at_done() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["messages"][0] == {"role": "system", "content": "sys"}
        assert body["stream"] is True
        lines = [
            'data: {"choices": [{"delta": {"content": "Hel"}}]}',
            'data: {"choices": [{"delta": {"content": "lo"}}]}',
            "data: [DONE]",
        ]
        return httpx.Response(200, text="\n".join(lines) + "\n")

    provider = _provider(handler)
    chunks = [c async for c in provider.stream_chat(system="sys", messages=[("user", "hi")], max_tokens=50, timeout_s=5)]
    assert "".join(chunks) == "Hello"


async def test_stream_chat_raises_on_http_error() -> None:
    provider = _provider(lambda request: httpx.Response(500))
    with pytest.raises(AiUnavailableError):
        async for _ in provider.stream_chat(system="s", messages=[("user", "hi")], max_tokens=10, timeout_s=5):
            pass
