"""Opt-in tests against a REAL local Ollama. Skipped unless OLLAMA_LIVE_TESTS=1 (and OLLAMA_LIVE_MODEL names a model
you have pulled). They assert on shape, never on wording — a real model's text is not deterministic."""

from __future__ import annotations

import os

import pytest

from app.modules.ai.provider import AiUnavailableError, OllamaProvider
from tests.conftest import make_settings, signed_in
from tests.problems_helpers import HIDDEN_ANSWER, HIDDEN_SENTINEL, insert_problem
from tests.test_ai import parse_sse

BASE_URL = os.environ.get("OLLAMA_LIVE_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_LIVE_MODEL", "")

pytestmark = pytest.mark.skipif(
    os.environ.get("OLLAMA_LIVE_TESTS") != "1" or not MODEL, reason="set OLLAMA_LIVE_TESTS=1 and OLLAMA_LIVE_MODEL"
)

GENEROUS = 180  # a cold model load on CPU can take a while


async def test_generate_returns_real_text() -> None:
    result = await OllamaProvider(BASE_URL, MODEL).generate(
        system="Answer in one short sentence.", prompt="What is a hash map?", max_tokens=60, timeout_s=GENEROUS
    )
    assert result.text.strip()
    assert result.duration_ms > 0


async def test_stream_chat_yields_several_tokens_that_join_to_the_reply() -> None:
    tokens = [
        token
        async for token in OllamaProvider(BASE_URL, MODEL).stream_chat(
            system="Be brief.", messages=[("user", "Count from 1 to 5.")], max_tokens=40, timeout_s=GENEROUS
        )
    ]
    assert len(tokens) > 1
    assert "".join(tokens).strip()


async def test_max_tokens_really_bounds_the_reply() -> None:
    short = await OllamaProvider(BASE_URL, MODEL).generate(
        system="Write a very long essay.", prompt="Explain sorting algorithms.", max_tokens=8, timeout_s=GENEROUS
    )
    assert len(short.text) < 200


async def test_an_unreachable_server_raises_instead_of_inventing_an_answer() -> None:
    dead = OllamaProvider("http://127.0.0.1:9", MODEL)  # nothing listens on the discard port
    with pytest.raises(AiUnavailableError):
        await dead.generate(system="s", prompt="p", max_tokens=5, timeout_s=3)
    with pytest.raises(AiUnavailableError):
        _ = [t async for t in dead.stream_chat(system="s", messages=[("user", "p")], max_tokens=5, timeout_s=3)]
    assert await dead.is_reachable(timeout_s=1) is False


async def test_a_model_that_is_not_pulled_is_unavailable_not_a_crash() -> None:
    missing = OllamaProvider(BASE_URL, "definitely-not-a-real-model:0b")
    with pytest.raises(AiUnavailableError):
        await missing.generate(system="s", prompt="p", max_tokens=5, timeout_s=GENEROUS)


async def test_the_whole_stack_hint_and_chat_against_the_real_model(build_app) -> None:
    settings = make_settings(ollama_model=MODEL, ollama_base_url=BASE_URL, ai_request_timeout=GENEROUS)
    app = await build_app(settings, ai_provider=OllamaProvider(BASE_URL, MODEL))
    await insert_problem(app, "two-sum")
    async with signed_in(app, username="ada") as (client, auth):
        hint = await client.post(
            "/api/ai/hint",
            json={"problem_slug": "two-sum", "language": "python", "code": "def solve(a, t):\n    pass\n"},
            headers=auth,
            timeout=GENEROUS,
        )
        assert hint.status_code == 200, hint.text
        assert hint.json()["content"].strip() and hint.json()["model"] == MODEL
        assert HIDDEN_SENTINEL not in hint.text and HIDDEN_ANSWER not in hint.text

        chat = await client.post(
            "/api/ai/conversations", json={"message": "Say hello."}, headers=auth, timeout=GENEROUS
        )
        events = parse_sse(chat.text)
        assert events[0][0] == "start" and events[-1][0] == "done"
        assert sum(1 for name, _ in events if name == "token") > 1
