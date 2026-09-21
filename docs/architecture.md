# Architecture

## Overview

```
                        Internet / browser
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Caddy (reverse     │  the ONLY published service
                    │  proxy)             │
                    └───────┬─────┬───────┘
              /api/*        │     │        everything else
                            ▼     ▼
                  ┌──────────────┐ ┌────────────────┐
                  │ FastAPI      │ │ Next.js        │
                  │ (apps/api)   │ │ (apps/web)     │
                  └──┬─────┬─────┘ └────────────────┘
                     │     │
            ┌────────┘     └────────┐
            ▼                       ▼
     ┌────────────┐          ┌────────────┐        ┌──────────────┐
     │ PostgreSQL │          │   Redis    │        │ Ollama (opt.)│  ← phase 5
     └────────────┘          └─────┬──────┘        └──────────────┘
                                   │  queue "judge" (Celery)
                                   ▼
                          ┌────────────────┐        ┌──────────────────┐
                          │ Judge worker   │───────▶│ dedicated sandbox │
                          │ (apps/judge)   │        │ Docker daemon     │
                          └────────────────┘        └──────────────────┘
```

Build status: **phases 1–5 (foundation, problem platform, SahuJudge, profiles, SahuCodeX AI)** are implemented —
everything drawn above except Qdrant, MinIO and the metrics stack. The API talks to Ollama over HTTP — a local model, no
paid service — see [ai.md](ai.md). The judge worker talks to its own, isolated Docker daemon (never the host's
socket, never the application's) — see [judge.md](judge.md). See the [README](../README.md#roadmap).

## Repository layout

```
apps/web         Next.js 16 (App Router, TypeScript, Tailwind v4)
apps/api         FastAPI service (modular monolith)
apps/judge       SahuJudge — the Celery worker, sandbox driver and verdict engine (docs/judge.md); shares apps/api's
                 models and settings rather than duplicating them
packages/shared  Types/constants shared by the web app (brand, roles, nav, API error shape)
database/        Alembic migrations (database/migrations) and seed scripts (database/seeds)
infrastructure/  Dockerfiles + Caddyfile (docker/), Prometheus and Grafana config (phase 8)
docs/            This documentation
```

Two deliberate details:

* Alembic's `alembic.ini` lives in `apps/api` (it needs the app's models on `sys.path`) but the migration scripts live in
  the top-level `database/migrations`, as specified. `script_location` bridges the two, and the Docker image mirrors the
  repo layout (`/srv/apps/api`, `/srv/database`) so the relative path works unchanged in and out of containers.
* Dockerfiles live in `infrastructure/docker/` and build from the repository root, because both images need files from
  several top-level directories (npm workspaces for the web app; `database/` for the API).

## Backend: a modular monolith

`apps/api/app` is organised by feature module, not by technical layer:

```
app/
  main.py            application factory  (create_app)
  asgi.py            uvicorn entrypoint
  db_models.py       imports every model so Alembic sees the full metadata
  core/              cross-cutting infrastructure — config, db, security, rate limiting, errors,
                     logging, metrics, middleware, email, pagination
  modules/
    auth/            registration, login, refresh rotation, sessions, email/password flows
    users/           users, profiles, roles; public profile
    admin/           admin-only API (RBAC-guarded)
    audit/           append-only audit trail
    health/          /health, /ready, /metrics
    problems/        problems, tags, test cases, languages, progress: search, filters, caching, admin authoring
    submissions/     submit/run API, history, the event WebSocket — enqueues jobs onto Redis; never executes code
                     itself (see apps/judge)
    profiles/        streaks and the achievement catalogue: models, the check functions SahuJudge calls after
                     judging, and the public GET /users/{username}/stats aggregation
    ai/              SahuCodeX AI: the provider protocol + Ollama client, prompt builders, conversations, usage
                     metering, and the hint/explain/review/chat routes (streaming over Server-Sent Events)
```

Each module owns `models.py` (SQLAlchemy), `schemas.py` (Pydantic, the only shapes that leave the API), `service.py`
(business logic, no HTTP types) and `router.py` (HTTP glue). Later phases add `contests`, `leaderboard`,
`discussions`, `notifications` and `analytics` the same way — modules are added when they have real behaviour, not
stubbed early.

### Request lifecycle

`RequestContextMiddleware` (request id, structured access log, Prometheus metrics) → `CORSMiddleware` →
`SecurityHeadersMiddleware` → `BodySizeLimitMiddleware` → router. The `/api` router applies a per-IP rate limit to every
route; individual routes add their own limits (login, registration, password reset, submit, run). All middleware is
pure ASGI so streaming responses (AI, phase 5) and the event WebSocket (`GET /api/ws`, mounted at the app root — a
WebSocket handshake has no `Authorization` header, so it authenticates with a short-lived ticket instead) are never
buffered.

Sessions are explicit: services call `await db.commit()` themselves. Anything uncommitted is rolled back when the
request-scoped session closes, so a failed request cannot leave half-written state.

## Key decisions

| Decision | Why |
|---|---|
| **Caddy in front, not Next.js rewrites** | The API must know each caller's real IP (rate limiting, audit log). Next.js's `rewrites()` proxy forwards `X-Forwarded-For` *unchanged* — so a client could send `X-Forwarded-For: 6.6.6.6` and be believed, or, with no header, every user would appear as the web container. Caddy overwrites the header with the true client address (verified against a real Caddy binary). `TRUSTED_PROXY_COUNT=1` then trusts exactly one hop. The Next.js rewrite remains only for `npm run dev`, where the API ignores forwarded headers. |
| **Access token in memory, refresh token in an httpOnly cookie** | XSS can't read a long-lived credential; the short-lived access token disappears on reload and is re-minted from the cookie. See [authentication.md](authentication.md). |
| **JWTs carry no roles** | Authorization is evaluated against the database on every request, so demotions, bans and session revocation take effect immediately, not when a token expires. |
| **Redis for rate limits and the revoked-session denylist** | Both need fast shared state with TTLs. Rate limiting fails *open* on a Redis outage (availability); the denylist fails *closed* (a revoked session must not be honoured). |
| **`/health`, `/ready`, `/metrics` at the root, not under `/api`** | They are for orchestrators and Prometheus. Caddy only routes `/api/*` to the backend, so they are never reachable from outside. |
| **SQLite + fakeredis for the fast test suite; PostgreSQL for verification** | Tests run anywhere in seconds. Setting `TEST_DATABASE_URL` runs the identical suite (and the migration-vs-model drift check) against real PostgreSQL. |
| **Problem statements are data, rendered without raw HTML** | Statements and editorials are admin-authored Markdown shown to every learner. `react-markdown` renders them without `rehype-raw`, drops images, and opens links with `noopener noreferrer`, so a hostile or careless statement cannot execute script. |
| **Nonce-based CSP set in `src/proxy.ts`** | No `unsafe-inline` for scripts. The nonce forces server rendering, which is fine for an app that is almost entirely authenticated. |
| **The judge worker gets its own Docker daemon, never the host's socket** | Mounting `/var/run/docker.sock` into anything that handles user input would hand a worker compromise root on the host. The dedicated daemon holds no application secrets, is reachable only from the worker over an isolated network, and runs rootless. See [judge.md](judge.md#the-docker-socket-problem-and-the-decision-made). |
| **A "Run" is not a "Submission"** | Run (the editor's quick-check button) is ephemeral: a short-lived Redis record, no database row, no effect on progress or counters — a user iterating on a solution shouldn't create submission history or consume the judge's durable storage. A Submit is graded against hidden tests too and is permanent. Both share the same engine and sandbox. |
| **The event WebSocket authenticates with a minted ticket, not the access token** | A WebSocket handshake cannot carry an `Authorization` header, and putting the token in the URL would leak it into proxy logs. `POST /api/ws/ticket` mints a random, single-use, 30-second, user-bound ticket (stored only as a hash) that the socket redeems once. |
| **Profile stats, streaks and achievements are public, not owner-only** | `GET /api/users/{username}/stats` needs no auth, the same as the public profile it sits beside — matching how GitHub/LeetCode show activity publicly. A user's *submissions* (their source code) stay owner-only; only aggregate counts, dates and achievement names are public. |
| **`img-src` allows any `https:` host, for user-set avatar URLs** | There is no file upload or storage abstraction yet (planned for phase 8), so an avatar is a plain URL the user supplies. Images cannot execute script, so allowing any HTTPS host is the standard low-risk way to support this without a per-host allow-list or a proxy. |
| **AI chat streams over plain HTTP (Server-Sent Events), not the WebSocket** | The reply is one request's response, so a normal `fetch` streams it and can send the `Authorization` header — no ticket dance, no long-lived socket, and it works through Caddy unbuffered. The submissions WebSocket exists because judging finishes *later, elsewhere* (a worker); an AI reply is produced during the request. |
| **Hint / Explain / Review are one-shot; only chat streams and is stored** | They are read once, in full, and are not conversations; streaming them would add UI state for no benefit. Chat is where seeing the reply arrive matters, and where history is useful. One-shots leave only a usage row. |
| **The AI gets problem context by slug, resolved server-side, from the public shape only** | The client never sends statement text, and the server builds the prompt from `ProblemPublic` — the same object the public API returns, which has no field for hidden tests or the editorial. Leaking them would need a bug where `ProblemPublic` is built, not in the AI code. |
| **AI persistence runs in a cancellation-shielded `finally`** | Pressing Stop or closing the tab cancels the stream generator. The partial reply and the usage row are still written, because an abandoned request costs the model as much as a finished one. |
| **AI failures are 503s, never placeholder text** | With no model configured, an unreachable server or a timeout, every AI route answers `503 AI_UNAVAILABLE` (or an in-band `error` event mid-stream) and the UI says so. Nothing pretends to be a model reply. |

## Frontend

App Router with server components for static shells (landing, auth pages) and client components where interaction is
required (forms, dashboard, command palette). State: TanStack Query for server data, Zustand for the in-memory session.

* `lib/api/http.ts` — low-level fetch wrapper, normalises the API error envelope into `ApiError`.
* `lib/auth/session.ts` — login/logout and the **single-flight, cross-tab-safe token refresh**. Refresh tokens rotate,
  so two simultaneous refreshes with one cookie look like theft; requests are de-duplicated within a tab and serialised
  across tabs with the Web Locks API, and the server tolerates a short race window.
* `lib/api/client.ts` — authenticated `api()` wrapper: attaches the token, refreshes once on `TOKEN_EXPIRED`, signs the
  user out locally if the session was revoked.
* `src/proxy.ts` — redirects (signed-out → `/login`, signed-in → away from `/login`) using a non-secret *hint* cookie,
  plus the CSP. The hint is UX only; the API re-authorises every call.
* `components/problems/` is the coding workspace. Monaco is loaded only on that page (`next/dynamic`, `ssr: false`) and is
  **self-hosted** from `public/monaco` (copied at build time), so it needs no CDN. Public pages (`/problems`) use
  `apiPublic()`, which personalises when signed in but never forces a login.
* `lib/submissions/` is SahuJudge's client: `api.ts` (submit/run/history, all polling while something is still being
  judged), `socket.ts` (`useJudgeSocket` — the event WebSocket, with polling as the fallback if it never connects, e.g.
  a proxy that doesn't forward the upgrade). The workspace (Run/Submit) and `/submissions[, /:id]` both use these; a
  submission's own detail page is the only place a user's own source code and compiler output are shown back to them.
* `components/profiles/` (solved breakdown, streak card, achievements grid, a hand-rolled GitHub-style activity
  calendar — no charting library) is shared between `/profile/[username]` and the dashboard's own stats section, both
  reading `GET /users/{username}/stats` through `lib/profiles/api.ts`. `components/settings/` is the self-service form
  for the fields `PATCH /users/me` accepts.
* `components/ai/` (the Assistant page, conversation list, chat thread and composer, and the workspace's AI tab) and
  `lib/ai/` (`stream.ts` + `sse.ts` — a `fetch` streaming client with an incremental SSE parser that handles frames split
  anywhere, including mid-UTF-8 character; `use-chat.ts` — the send/stream/stop state machine; `api.ts` — queries). AI
  output goes through the shared `Markdown` component, which now also gives fenced code blocks a Copy button.
* Features that ship in later phases appear in navigation as disabled items, never as links to a 404
  (`packages/shared` → `NAV_ITEMS[].available`).
