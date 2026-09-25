# SahuCodeX

**Code. Compete. Learn.**

An AI-powered coding and competitive-programming platform: an online judge (**SahuJudge**), contests, a developer
community, and a local, open-source AI assistant (**SahuCodeX AI**). Everything runs on free/open-source software and
works locally with **no paid API keys**.

> **Status: build phase 8 of 8 — Advanced.** Accounts and sessions (phase 1), 30 original problems in a Monaco
> workspace (phase 2), **SahuJudge** grading real code in an isolated sandbox (phase 3), public profiles with streaks
> and achievements (phase 4), **SahuCodeX AI** hints/reviews/chat from a local Ollama model (phase 5), **Contests**:
> timed, ICPC-style contests with standings computed live from the same SahuJudge verdicts (phase 6), **Community**:
> per-problem discussions, voting, reports and moderation (phase 7), and now **Advanced**: personalised
> recommendations, cached contest standings, **RAG** (semantic "similar problems" search and retrieval-augmented AI
> chat context, on [Qdrant](https://qdrant.tech)), and Prometheus metrics. See the [roadmap](#roadmap) for exactly
> what shipped in this phase. The UI shows unbuilt features as disabled, never as fake data.

## What works today

| | |
|---|---|
| **Landing page** | Brand, tagline, calls to action; dark by default, light/system themes, responsive |
| **Accounts** | Register, sign in (email or username), sign out, forgot/reset password, email verification |
| **Sessions** | Short-lived access token + rotating httpOnly refresh cookie with reuse detection, multi-tab safe; see and sign out other devices |
| **Authorization** | `USER` / `MODERATOR` / `ADMIN` roles enforced server-side; an admin-only user listing API |
| **Problems** | 30 original problems (10 easy / 12 medium / 8 hard, 23 topics). Full-text search, filters (difficulty, topics, solved/unsolved, acceptance rate), sorting, pagination — all in the URL |
| **Coding workspace** | Statement, examples, step-by-step hints and a locked editorial next to a self-hosted **Monaco** editor (Python, C++, JavaScript), autosaved drafts, font/wrap/minimap preferences; tabs on phones |
| **SahuJudge** | Run your code against custom input, or Submit to judge it against public *and* hidden tests, in an isolated, non-root, network-less sandbox container — one per execution, destroyed after. Deterministic verdicts (`ACCEPTED`, `WRONG_ANSWER`, `TIME_LIMIT_EXCEEDED`, `MEMORY_LIMIT_EXCEEDED`, `RUNTIME_ERROR`, `COMPILATION_ERROR`, `SYSTEM_ERROR`), live updates over an authenticated WebSocket, submission history and detail pages. Hidden tests never reach the browser |
| **Profiles** | A public profile per user (`/profile/username`): solved problems by difficulty, submission totals and acceptance rate, a current/longest solving streak, 8 achievements (earned and locked), a 365-day activity calendar. A settings page to edit your bio, country, website, GitHub and avatar URL |
| **SahuCodeX AI** | **AI Hint** (progressive, never the solution), **AI Review** and **Explain** in the workspace, on their own *"a suggestion, not a verdict"* tab; a streaming **Assistant** chat with saved, renameable conversations and copyable code blocks. Runs on a local Ollama model you choose (`OLLAMA_MODEL`); unconfigured or unreachable, it says so — never a canned reply. The model only ever sees the public statement and your code, never hidden tests. Rate-limited, size-capped, metered. See [docs/ai.md](docs/ai.md) |
| **Contests** | Timed, ICPC-style contests: problems stay hidden until `start_time`, registration is open until `end_time`, and standings (points, penalty, tiebreak) are computed live from SahuJudge's own verdicts on every request, briefly cached to absorb concurrent viewers — never stored otherwise, never client-supplied. Register-gated Submit/Run reuse the exact same judge pipeline as the plain workspace; AI assistance is switched off for fairness while a contest runs. Admins create, edit (locked once started) and publish contests, including which problems and how many points each is worth. See [docs/contests.md](docs/contests.md) |
| **Community** | Per-problem discussion threads and replies, up/down voting, reporting, in-app notifications, and a MODERATOR-gated moderation queue (remove content via a report, or lock a thread directly). See [docs/community.md](docs/community.md) |
| **Recommendations** | A personalised "what to solve next" on the dashboard, ranked from your own solved-tag history and difficulty progression — purely content-based, no other user's data is ever read |
| **RAG** | Semantic "similar problems" on the problem detail page, a `/search/semantic` endpoint, and retrieval-augmented context in SahuCodeX AI chat — all on [Qdrant](https://qdrant.tech) + Ollama embeddings, optional exactly like AI itself. See [docs/rag.md](docs/rag.md) |
| **Admin** | Problem editor (create/edit, public and hidden tests, starter code, hints, editorial, readiness check, publish/unpublish/archive/restore — hidden tests never reach learners), contest authoring, and live analytics (platform totals, 30-day AI usage) |
| **Dashboard** | Real data from the API: your account, verification state, active sessions, solved/streak/achievement summary, recommended problems |
| **Navigation** | Desktop + mobile nav, `Ctrl+K` command palette, theme switcher |
| **Platform** | Redis rate limiting and read-through caching, structured logging with secret redaction, `/health` `/ready` `/metrics` (Prometheus), optional Grafana dashboard, security headers + CSP, Alembic migrations, seed data, Caddy reverse proxy |
| **Tests** | 484 API tests (same suite on SQLite and real PostgreSQL; includes brute-force verification of every seed-problem solution) plus 6 opt-in tests against a real Ollama, 138 judge tests on SQLite + fakeredis (39 more need a real Docker daemon — not run in this environment, see [docs/judge.md](docs/judge.md)), 287 web unit/component tests, 66 browser end-to-end tests (the AI ones run against a real local model, unmocked) |

## Architecture

```
 browser ─► Caddy ─┬─ /api/*  ─► FastAPI ─┬─► PostgreSQL
                   └─ others  ─► Next.js  ├─► Redis  ──► Celery judge worker ─► dedicated sandbox daemon
                                          ├─► Ollama (local model, optional — chat + embeddings)
                                          └─► Qdrant (vector search, optional)

              Prometheus (optional) ── scrapes GET /metrics ──► Grafana (optional)
```

Details and the reasoning behind each choice: [docs/architecture.md](docs/architecture.md).

## Stack

Next.js 16 (App Router) · TypeScript · Tailwind CSS v4 · shadcn/ui-style components on Radix · TanStack Query · Zustand ·
FastAPI · Pydantic · SQLAlchemy 2 (async) · Alembic · PostgreSQL 16 · Redis · Celery · Caddy · Docker Compose ·
Monaco Editor · Ollama · Qdrant · Prometheus · Grafana · pytest · Vitest · Playwright. Not built: MinIO/object storage
(see [docs/architecture.md](docs/architecture.md)'s notes on avatar URLs), Recharts (the admin analytics UI uses
plain tables, not charts, at its current scale).

## Requirements

* **Docker** with Compose v2 (easiest), *or*
* Node.js ≥ 20, Python ≥ 3.12, PostgreSQL 16 and Redis 7 for a manual setup. (PostgreSQL is needed for full-text search; other
  databases only do substring matching.)

## Quick start (Docker)

```bash
cp .env.example .env          # review it; the DEV ONLY values are fine locally
docker compose up --build
```

Open **http://localhost:3000**. If port 3000 is taken, set `WEB_PORT` and `PUBLIC_URL` in `.env` (see
[troubleshooting](docs/troubleshooting.md#port-3000-is-already-in-use)).

Development accounts are seeded on first start (from `.env.example`; **development only**):

| Role | Email | Username | Password |
|---|---|---|---|
| Admin | `admin@example.com` | `sahuadmin` | `Admin-dev-password-1` |
| Demo user | `demo1@example.com` | `demo1` | `Demo-dev-password-1` |
| Demo user | `demo2@example.com` | `demo2` | `Demo-dev-password-2` |

Verification and password-reset emails are printed to the API log in development:
`docker compose logs backend | grep -A6 "DEV MAILBOX"`.

Sign in as the admin to open **Admin → Problems**. Useful URLs: the app `http://localhost:3000` · API docs `http://localhost:3000/api/docs` · API on loopback
`http://127.0.0.1:8000/health` and `/ready`.

> **Heads-up:** the Docker files were written carefully but could not be executed in the environment this phase was
> built in (no Docker available). Every component they wrap was run and tested individually — see
> [docs/security.md](docs/security.md#what-has-not-been-verified). If `docker compose up` misbehaves, please tell me what
> you see.

## Manual setup (no Docker)

You need PostgreSQL and Redis running and reachable at the URLs in `.env`.

```bash
cp .env.example .env

# API — terminal 1
cd apps/api
pip install -r requirements-dev.txt
python -m alembic upgrade head            # create the schema
python ../../database/seeds/run.py        # seed the dev users, 23 topics and the 30 problems (optional)
python -m uvicorn app.asgi:app --reload   # http://localhost:8000/api/docs

# Web — terminal 2, from the repository root
npm install
npm run dev:web                           # http://localhost:3000  (copies the Monaco editor into public/monaco first)
```

In this mode Next.js proxies `/api/*` to the API (`API_INTERNAL_URL`).

## Configuration

All configuration is environment variables; [.env.example](.env.example) documents every one. The important ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL`, `REDIS_URL` | Service connections (compose overrides them with in-network hosts) |
| `JWT_SECRET` | ≥ 32 chars. **Production refuses placeholders.** `openssl rand -hex 32` |
| `JWT_ACCESS_EXPIRE`, `JWT_REFRESH_EXPIRE` | Token lifetimes, e.g. `15m`, `7d` |
| `CORS_ORIGINS`, `PUBLIC_URL` | Allowed browser origin(s); also the CSRF allow-list |
| `TRUSTED_PROXY_COUNT` | Reverse proxies in front of the API (compose: 1) |
| `RATE_LIMIT_*` | Per-route limits, format `5/minute`; `RATE_LIMIT_ENABLED=false` to disable |
| `EMAIL_BACKEND` | `console` (dev) or `smtp` |
| `OLLAMA_MODEL` (+ `OLLAMA_BASE_URL`, `AI_*`, `RATE_LIMIT_AI`) | SahuCodeX AI. No model is hardcoded; empty = AI answers "not configured" and the rest works — see [docs/ai.md](docs/ai.md) |
| `SANDBOX_DOCKER_HOST` | The **dedicated** Docker daemon SahuJudge runs sandboxes in — never the host's socket. Set for you in compose |
| `MAX_INFLIGHT_SUBMISSIONS`, `RATE_LIMIT_SUBMIT`, `RATE_LIMIT_RUN`, `JUDGE_STALE_AFTER` | SahuJudge abuse and cleanup limits — see [docs/judge.md](docs/judge.md) |

## Database

PostgreSQL, migrated with Alembic (`database/migrations`). Compose applies migrations on start. Manually:
`python -m alembic upgrade head` from `apps/api`. Schema and conventions: [docs/database.md](docs/database.md).

## Ollama (optional — enables SahuCodeX AI)

```bash
docker compose --profile ai up -d ollama
docker compose exec ollama ollama pull <model-name>      # any model you like
# .env:  OLLAMA_MODEL=<model-name>
```

Or install Ollama on your host and keep `OLLAMA_BASE_URL=http://localhost:11434` (with compose, also set
`COMPOSE_OLLAMA_URL=http://host.docker.internal:11434`). Then restart the API; the workspace's AI buttons and `/ai` come
alive. Everything else works without it. Details, limits and known limitations: [docs/ai.md](docs/ai.md).

## Development

```bash
npm run lint:web && npm run typecheck        # web
cd apps/api && python -m ruff check . && python -m ruff format .   # api
```

Project layout:

```
apps/web         Next.js frontend            apps/api        FastAPI backend (modular monolith)
apps/judge       SahuJudge: worker, sandbox   packages/shared Types/constants shared by the web app
                 driver, verdict engine
database/        migrations + seeds          infrastructure/ Dockerfiles, Caddyfile, Prometheus/Grafana (phase 8)
docs/            documentation
```

## Testing

```bash
cd apps/api && python -m pytest                    # hermetic: SQLite + fakeredis, ~6 s
TEST_DATABASE_URL=postgresql://user@localhost:5432/sahucodex_test python -m pytest   # same suite on PostgreSQL
cd apps/judge && python -m pytest                   # SahuJudge: checkers, verdicts, worker pipeline (SQLite + fakeredis)
SJX_DOCKER_TESTS=1 python -m pytest -m docker        # + the mandatory sandbox security tests (needs a Docker daemon)
npm run test:web                                    # Vitest unit + component tests
npx playwright install chromium                     # once
E2E_BASE_URL=http://localhost:3000 npm run test:e2e -w @sahucodex/web   # browser tests; stack must be running
```

The e2e suite registers many users from one IP; start the API with relaxed rate limits (see
[troubleshooting](docs/troubleshooting.md#too-many-requests-429-rate_limited-while-developing)).

## Deployment

[docs/deployment.md](docs/deployment.md) has the production checklist (HTTPS, secrets, proxy trust, backups).

## Documentation

[architecture](docs/architecture.md) · [problems](docs/problems.md) · [database](docs/database.md) · [api](docs/api.md) ·
[authentication](docs/authentication.md) · [security](docs/security.md) · [judge](docs/judge.md) (design) ·
[ai](docs/ai.md) · [contests](docs/contests.md) · [community](docs/community.md) · [rag](docs/rag.md) ·
[web preview](docs/web-preview.md) (design, not in the roadmap) ·
[deployment](docs/deployment.md) · [troubleshooting](docs/troubleshooting.md)

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| **1** | Foundation: monorepo, auth, RBAC, web shell, health, migrations, Docker | **Done** |
| 2 | Problem platform: problems, tags, search/filters, Monaco editor, admin problem editor, 30 original problems | **Done** |
| 3 | SahuJudge: submissions, Redis/Celery queue, sandboxes (Python, C++, JS), verdicts, WebSocket updates | **Done** |
| 4 | Profiles, statistics, streaks, achievements, activity calendar, dashboard stats | **Done** |
| 5 | SahuCodeX AI: hints, explain, review, debug, chat, streaming, rate limits | **Done** |
| 6 | Contests: creation, registration, timer, scoring, penalties, live standings | **Done** |
| 7 | Community: discussions, voting, reports, notifications, moderation | **Done** |
| 8 | RAG, recommendations, caching, analytics, Prometheus/Grafana, performance | **Done** |

### Known limitations / TODO

**Phase 8**

* **RAG has no backfill job.** A problem published or last edited before `QDRANT_URL` was set is not retroactively
  indexed; re-saving it through the admin editor indexes it (indexing runs synchronously on save, not as a
  background job — see [docs/rag.md](docs/rag.md#known-limitations)).
* **Recommendations and RAG candidate ranking both happen in Python after a DB fetch**, not in SQL. Fine at this
  platform's actual problem-set size (dozens, not thousands); the seam to move it into SQL is noted at both
  call sites if the catalog ever grows large enough to matter.
* **Contest standings caching is a 5-second Redis cache, not a stored snapshot.** Standings are still computed
  fresh from `submissions` on every cache miss — nothing new is persisted; this only absorbs a burst of concurrent
  viewers within the frontend's existing 20s poll interval. The "no `leaderboards` snapshot table" limitation from
  phase 6 (below) still applies.
* **The `docker-compose.yml` `qdrant` service was never booted** (no Docker in the environment this was built in,
  same as `sandbox`/`judge`/`ollama` before it) — parses as valid YAML; verified instead with an in-process
  `qdrant-client` in the test suite. Prometheus/Grafana configs under `infrastructure/` are similarly unbooted.
* **Analytics** (`GET /api/admin/analytics`, `/admin/analytics` in the UI): platform totals (users, published
  problems, submissions, published contests, discussions) plus a 30-day summary of `AiUsage` — the rows recorded
  since phase 5 that nothing read until now (requests/failures/avg duration per AI feature). Everything is a live
  aggregate query, computed on every request, never stored or pre-aggregated — there is no separate metrics
  warehouse. Infrastructure-level metrics (request rate, latency, memory) are the existing Prometheus `/metrics`
  endpoint plus the Grafana dashboard below, a different layer from this admin-facing usage summary.
* Full details on RAG specifically: [docs/rag.md](docs/rag.md).

**Phase 6**

* **No `contest.started`/`ending`/`finished` WebSocket events.** The design sketch called for these; the frontend
  instead derives a contest's phase client-side from `start_time`/`end_time` (a live `Countdown`, refetching on
  expiry and polling standings every 20s while running). Simpler, and a contest's phase needs no server push at
  all since the client already has the timestamps — revisit only if contests need tighter live synchronisation.
* **No `leaderboards` snapshot table.** Standings are cheap enough to compute live, on every request, from
  `submissions` that freezing a copy at contest end was not worth adding yet.
* Penalty rules for `COMPILATION_ERROR`/`SYSTEM_ERROR` (never an attempt, never a penalty) are fixed, not the
  "per-contest setting" the original design sketch described.
* **AI assistance is off during a contest** (the workspace hides the SahuCodeX AI tab entirely) for fairness between
  participants — a deliberate scope addition beyond the original sketch, not a gap.
* No contest deletion (draft or published) — only publish/unpublish. Matches how problems work (archive, not delete).
* Full details and what was and wasn't verified: [docs/contests.md](docs/contests.md).

**Phase 5**

* **AI quality is the model's quality.** Verified with a 3B-parameter model, which is fast on a laptop but fallible: an
  early review invented two bugs and called correct code "correctly implemented". The review prompt was tightened
  (mandatory "I can't run this code" opener, bugs only with a concrete failing input, verdict words banned) and re-checked
  against the real model, but that lowers the risk rather than removing it — which is why AI output is always labelled a
  suggestion and the judge decides. Use a larger model if you can. Details: [docs/ai.md](docs/ai.md#known-limitations).
* **The Docker Compose wiring for Ollama was never booted** (no Docker here): the `ollama` service and the API's override
  to reach it by name parse as valid YAML, but were not run. Host-installed Ollama with the host-run API is what was tested.
* AI Review may show a corrected solution in its "Possible optimisations" section; only AI Hint is spoiler-restricted.
* Hints given this visit are remembered by the page, not the server — a reload restarts the hint sequence.
* The first request after Ollama has been idle is slow (the model reloads; ~9 s for a 3B model here). Raise
  `AI_REQUEST_TIMEOUT` for larger models.
* One shared AI rate budget (`RATE_LIMIT_AI`) rather than per-feature; `AiUsage` rows are recorded (see phase 8's
  known limitations above for what reads them).
* The **Debugger** is a chat quick-start template, not a separate endpoint. **RAG** (semantic search,
  retrieval-augmented chat context) shipped in phase 8 — see [docs/rag.md](docs/rag.md).
* No GPU passthrough block in the compose file.

**Phase 4**

* Streaks and achievements are written by SahuJudge after judging (see phase 3's caveat below) — **without a running
  judge worker, solving a problem never updates them**, the same limitation as submission grading itself.
* No file upload for avatars: `avatar_url` is a plain URL field (any `https://` image host). A storage abstraction
  (local disk or MinIO) is planned for phase 8.
* The 8 achievements are a fixed, hand-picked set (`apps/api/app/modules/profiles/achievements.py`); there is no
  admin UI to add more yet — a new one is a code change plus a migration, like adding a language.
* There is no user directory / search-by-username page — only a direct profile link (`/profile/<username>`) or a
  link from elsewhere in the app. The command palette's "Search users" is now labelled for phase 7 (community),
  where discovering other users fits more naturally.
* The activity calendar counts every submission (any verdict), not just solves — matching GitHub's own "any commit
  counts" convention rather than a stricter "only accepted" one.

**Phase 3**

* **The Docker-dependent parts of SahuJudge were never run in this environment** (no Docker available where this was
  built): the runner image, both new Dockerfiles, the `sandbox`/`judge` compose services, and the 39
  `@pytest.mark.docker` / `@pytest.mark.linux` tests that need a real daemon or a Linux host. Everything they wrap was
  run individually (the worker pipeline against a trusted local sandbox double, the exact `docker` CLI arguments
  against a scripted fake). CI now runs the real Docker-backed tests on every push (not yet exercised here — no CI has
  run yet, see Phase 1 below). Full details: [docs/judge.md](docs/judge.md#what-has-not-been-run-locally).
* `POST /api/run`'s `mode=samples` (run every public example at once, capturing each one) is implemented and tested,
  but the workspace's Run button currently always uses `mode=custom` against whatever is in the input box — the
  console UI would need a second affordance to expose the samples mode.
* Only **Python, C++ and JavaScript** run; the language table (`apps/judge/sahujudge/languages.py`) is designed for
  more, but each needs a toolchain added to the runner image.
* Running more than one `judge` container needs `-B` (Celery beat, the periodic reaper) moved to exactly one replica
  — see [docs/deployment.md](docs/deployment.md#scaling-notes).

**Phase 2**

* *Format* only tidies whitespace for Python and C++ (no formatter is bundled); JavaScript uses Monaco's formatter.
* Admin now covers problems, tags, contests, discussion moderation (a separate `/moderation` area, MODERATOR-gated
  rather than ADMIN-only) and analytics. Still missing: user management, and audit-log/system-health pages.
* Monaco is ~24 MB of static files copied at build time; trimming unused languages would shrink the image.

**Phase 1**

* Docker artifacts (`docker compose up`, both original Dockerfiles) are unexecuted; Redis was exercised through
  `fakeredis`'s TCP server rather than Redis itself.
* Email verification is recorded but not enforced.
* Web image is not yet optimised (`next start` with all dependencies; Next.js standalone output would shrink it).
* No CI has run yet (workflow provided in `.github/workflows/ci.yml`; this repository has no git history/remote yet).
* Prometheus and Grafana directories are placeholders for phase 8.

## License

Not yet chosen. Add a `LICENSE` file before publishing.
