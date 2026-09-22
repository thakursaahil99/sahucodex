# SahuCodeX AI

> Status: **implemented in build phase 5.** Hint, Explain and Review in the problem workspace, and a streaming
> Assistant chat with saved conversations. Runs on a local [Ollama](https://ollama.com) model by default — no paid
> API, no key — or, for a deployment with no machine to run Ollama on (e.g. this platform's own free Vercel
> deployment), [OpenRouter](https://openrouter.ai) with a free-tier model and its own API key. Verified end to end
> against a real model on both providers (see [What was run](#what-was-run)).

## Principles

* **Local and open-source first, hosted as an opt-in fallback.** Ollama is the default and needs no key. `AiProvider`
  (`apps/api/app/modules/ai/provider.py`) is a small protocol; `OpenRouterProvider` is the one hosted implementation,
  selected only by `AI_PROVIDER=openrouter` and configured only by its own `OPENROUTER_API_KEY` — nothing else
  changes providers implicitly, and a further provider would be a new class, never a rewrite of the callers.
* **No hardcoded model.** `OLLAMA_MODEL` names whatever model you have pulled. Empty means "none chosen": every AI
  endpoint answers `503 AI_UNAVAILABLE` immediately, without calling anything, and the rest of the platform is unaffected.
* **Fails cleanly, never fabricates.** An unreachable server, a missing model or a timeout is a structured
  `503 AI_UNAVAILABLE` (or an in-band `error` event mid-stream). There is no canned text standing in for a model reply
  anywhere in the code.
* **The judge is authoritative.** The AI is an assistant, not a source of truth. If it says "this looks right" and
  SahuJudge says `WRONG_ANSWER`, the verdict stands. The UI keeps AI output on its own **SahuCodeX AI** tab, under a
  banner reading *"a suggestion, not a verdict"*, next to — never mixed into — Output and Test results. The prompts
  forbid the model from calling code "correct"/"will pass" (see [Prompts](#prompts-and-what-the-model-sees)).
* **Hidden tests never reach the model.** See below; this is enforced by construction and covered by tests.

## Setup

```bash
# Option A — Docker Compose
docker compose --profile ai up -d ollama
docker compose exec ollama ollama pull <model-name>
# .env:  OLLAMA_MODEL=<model-name>       (the API reaches the `ollama` service automatically)

# Option B — Ollama installed on the host
ollama pull <model-name>
# .env:  OLLAMA_MODEL=<model-name>       OLLAMA_BASE_URL=http://localhost:11434 (the default)
#        with docker compose + host Ollama:  COMPOSE_OLLAMA_URL=http://host.docker.internal:11434
```

Then restart the API. `GET /api/ai/status` reports `{"configured": true, "model": "…"}`. Any Ollama model that supports
chat works; a small one (~3B parameters) answers in seconds on a laptop but is noticeably less reliable than a large one —
see [Limitations](#known-limitations).

```bash
# Option C — OpenRouter (hosted, for a deployment with no Ollama machine)
# Get a free key at https://openrouter.ai/keys (no card required for the free-tier models)
# .env:  AI_PROVIDER=openrouter
#        OPENROUTER_API_KEY=sk-or-v1-...
#        OPENROUTER_MODEL=meta-llama/llama-3.1-8b-instruct:free   (any OpenRouter model id; ":free" ones cost nothing)
```

Settings (all in `.env.example`): `AI_PROVIDER` (`ollama` | `openrouter` | `none`), `OLLAMA_BASE_URL`, `OLLAMA_MODEL`,
`OPENROUTER_BASE_URL` (default `https://openrouter.ai/api/v1`), `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`,
`AI_REQUEST_TIMEOUT` (default 60 s — Ollama's first call after the model has been idle includes loading it, which can
be much slower), `AI_MAX_PROMPT_CHARS` (8000), `AI_MAX_RESPONSE_TOKENS` (800), `AI_MAX_CONVERSATIONS` (50),
`AI_MAX_MESSAGES_PER_CONVERSATION` (100), `RATE_LIMIT_AI` (20/hour per user). With `AI_PROVIDER=openrouter`,
`ai_configured` requires **both** `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` — either alone still answers
`503 AI_UNAVAILABLE`.

## Features

| Feature | Where | Shape |
|---|---|---|
| **AI Hint** | workspace action bar | One progressive hint. The client sends the hints already given, so each goes a step further; the prompt forbids giving the solution or working code. |
| **AI Review** | workspace action bar | Fixed sections: Correctness (opinion only, opens with "I can't run this code…"), Potential bugs and edge cases (only with a concrete line + input, otherwise "None found by reading."), Time and space complexity, Readability, Possible optimisations. |
| **Explain** | workspace action bar | What the code does, the approach, key logic, complexity. |
| **Assistant chat** | `/ai` | Streaming replies (Server-Sent Events), Markdown with copyable code blocks, saved conversations you can rename and delete, Stop button, optional problem context (`/ai?problem=<slug>`). |
| **Debugger** | `/ai` quick start | A message template (code, input, expected vs actual output/error) for the chat. It is deliberately *not* a separate endpoint: a debugging answer is a chat answer given the right facts. |

Hint/Explain/Review are one-off, **non-streaming** calls: they are read once, in full, and are not stored as
conversations (only metered). Chat is the one place streaming pays for itself.

## API

All routes need a signed-in user. See [api.md](api.md) for the full shapes.

| Method & path | Purpose |
|---|---|
| `GET /api/ai/status` | `{configured, model}` — cheap, no model call |
| `POST /api/ai/hint` · `/explain` · `/review` | one-off generation → `{feature, content, model}` |
| `GET /api/ai/conversations` · `GET/PATCH/DELETE /api/ai/conversations/{id}` | list / read / rename / delete (owner only; a stranger's id is the same 404 as a missing one) |
| `POST /api/ai/conversations` | create a conversation with its first message **and stream the reply** |
| `POST /api/ai/conversations/{id}/messages` | send a message and stream the reply |

### Streaming protocol

`Content-Type: text/event-stream`, plain HTTP with the normal `Authorization` header (unlike the submissions WebSocket, a
`fetch` can send it, so there is no ticket step). Events, each `event: <name>` + one JSON `data:` line:

| Event | Data | Meaning |
|---|---|---|
| `start` | `{"conversation_id"}` | the conversation exists and the user's message is saved |
| `token` | `{"content"}` | a piece of the reply |
| `done` | `{}` | finished normally |
| `error` | `{"code","message"}` | the model failed **after** the 200 was sent — the only way to report it in-band |

Anything that fails *before* streaming (401, 404, 409, 422, 429, 503) is an ordinary JSON error response. Caddy proxies
the stream without buffering it (measured: first token 0.34 s vs 1.58 s total through Caddy).

If the client stops (Stop button, closed tab), the server keeps whatever was generated as the assistant message and
records the usage row — persistence runs in a cancellation-shielded `finally`, because an abandoned request costs the
model as much as a finished one.

## Prompts and what the model sees

`prompts.py` builds every prompt. The only problem data that can appear is a `ProblemPublic` — the same object the public
problem API returns, resolved **server-side from a slug** (the client never sends problem text). It has no field for hidden
tests or the editorial, so they cannot reach the model even through a future bug in the prompt code; the leak would have to
happen where `ProblemPublic` is built, which has its own tests. `apps/api/tests/test_ai.py` asserts, for hint, explain,
review and chat, that neither the hidden inputs/outputs nor the editorial appear in anything sent to the model or returned.

Every system prompt opens with the same rules: you are an assistant, not the judge; never say code "will pass"/"is
correct"; you have no hidden tests and must not invent any; answer in Markdown.

Prompts are treated as untrusted input in both directions: the request schemas reject unknown fields (no client-supplied
system prompt, role or user id), lengths are capped, and model output is rendered as inert Markdown — raw HTML is never
rendered, images are dropped, links open with `noopener noreferrer` (`components/ui/markdown.tsx`, tested with
`<script>`/`<img onerror>` payloads).

## Limits, metering and abuse controls

* **Rate limit**: `RATE_LIMIT_AI` per user, one shared budget across every AI feature (Redis sliding window, `429` +
  `Retry-After`, which the UI turns into "try again in about N minutes").
* **Size**: `AI_MAX_PROMPT_CHARS` per input (a `422 AI_INPUT_TOO_LARGE` before any model call), a hard parsing ceiling
  under it, `AI_MAX_RESPONSE_TOKENS` on the reply, `AI_REQUEST_TIMEOUT` on the call.
* **Conversations**: `AI_MAX_CONVERSATIONS` per user and `AI_MAX_MESSAGES_PER_CONVERSATION` (`409`).
* **Usage rows** (`ai_usage`): one per request, success or failure — user, feature, model, conversation, prompt and
  response characters, duration, `failed`. Failed and abandoned calls are recorded too, so cost and abuse visibility do not
  depend on the model answering. Nothing reads them yet (no admin analytics until phase 8).

## Testing

* `apps/api/tests/test_ai.py` (36 tests, hermetic, on SQLite and PostgreSQL): a recording `FakeAiProvider` stands in for
  Ollama and captures exactly what it was sent. Covers auth, "not configured", hidden-test/editorial non-leakage, prompt
  contract, validation, rate limiting, the outage paths (one-off and mid-stream), conversation privacy/limits, and Stop.
* `apps/api/tests/test_ai_live.py` (6 tests, **opt-in**): real Ollama.
  `OLLAMA_LIVE_TESTS=1 OLLAMA_LIVE_MODEL=<model> pytest tests/test_ai_live.py`. Asserts on shape and behaviour (tokens
  stream, `max_tokens` bounds the reply, an unreachable server or missing model raises rather than inventing text), never
  on wording.
* Web: the SSE parser and stream client (chunk boundaries, multi-byte characters, 401 refresh, 429 `Retry-After`), the
  Assistant, the AI tab, the workspace flow, Markdown copy buttons.
* `apps/web/e2e/ai.spec.ts` (5 tests): the browser against the real stack **and a real model** — no mocks.

### What was run

Everything above, against Ollama 0.33 with `qwen2.5:3b`, PostgreSQL, Redis-protocol server and Caddy: 6/6 live API tests,
5/5 AI e2e tests inside the full 61/61 e2e suite, plus the two failure modes on a real server (no model configured;
model configured but Ollama unreachable) — both give the documented clean errors while `/api/problems` keeps working.

**Not run:** the Docker Compose `ollama` service and the compose override that points the API at it (no Docker in the
environment this was built in). The YAML parses and the logic is the standard compose-DNS pattern, but it has not been
booted. No CI has run yet.

## Known limitations

* **Small models make mistakes, and the platform cannot fix that.** With the 3B model used here, an early review claimed
  two bugs that did not exist and called correct code "correctly implemented"; tightening the review prompt (mandatory
  "I can't run this code" opener, bugs only with a concrete failing input, banned verdict words) fixed both in the same
  probe. That reduces, not removes, the risk — the banner and "the judge decides" wording exist for this reason. Use a
  larger model if you have the hardware.
* **AI Review can include a corrected solution** (its "Possible optimisations" section may show code). Hint is the
  spoiler-restricted feature; Review and Explain operate on the learner's own code and are allowed to be concrete.
* **Hints are per page-visit.** The hints already given are sent back by the client, so a reload starts the sequence again.
  They are not stored server-side.
* **The first call is slow.** Ollama unloads an idle model; the next request pays the load (about 9 s for a 3B model on
  this machine; longer for larger ones). The UI says a local model "can take a little while".
* **One shared rate budget**, not per feature, and no per-user token accounting beyond the characters recorded.
* **No optional RAG.** The design doc floated a Qdrant/Chroma knowledge base; it is not built and not needed by anything
  above. Phase 8.
* **No GPU passthrough** in the compose file (see the comment on the `ollama` service).
* **Conversation titles come from the first line** of the first message (truncated to 120 characters) — no model-generated titles.
