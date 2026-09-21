# SahuCodeX

**Code. Compete. Learn.**

An AI-powered coding and competitive-programming platform: an online judge (**SahuJudge**), contests, a developer
community, and a local, open-source AI assistant (**SahuCodeX AI**). Everything runs on free/open-source software and
works locally with **no paid API keys**.

> **Status: build phase 4 of 8 — profiles.** Accounts and sessions (phase 1), 30 original problems in a Monaco
> workspace (phase 2), **SahuJudge** running and grading real code in an isolated sandbox (phase 3), and now
> **profiles**: a public profile for every user with solved counts, a streak, achievements and a GitHub-style
> activity calendar, plus a settings page to edit your own. AI and contests are not built yet; see the
> [roadmap](#roadmap). The UI shows unbuilt features as disabled, never as fake data.

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
| **Admin problem editor** | Create/edit problems, public and hidden tests, starter code, hints and editorial; readiness check; publish, unpublish, archive, restore. Hidden tests never reach learners |
| **Dashboard** | Real data from the API: your account, verification state, active sessions, solved/streak/achievement summary |
| **Navigation** | Desktop + mobile nav, `Ctrl+K` command palette, theme switcher |
| **Platform** | Redis rate limiting, structured logging with secret redaction, `/health` `/ready` `/metrics`, security headers + CSP, Alembic migrations, seed data, Caddy reverse proxy |
| **Tests** | 376 API tests (same suite on SQLite and real PostgreSQL; includes brute-force verification of every seed-problem solution), 127 judge tests on SQLite + fakeredis (39 more need a real Docker daemon — not run in this environment, see [docs/judge.md](docs/judge.md)), 191 web unit/component tests, 56 browser end-to-end tests |

## Architecture

```
 browser ─► Caddy ─┬─ /api/*  ─► FastAPI ─┬─► PostgreSQL
                   └─ others  ─► Next.js  └─► Redis  ──► Celery judge worker ─► dedicated sandbox daemon
                                                └──────(phase 5)─► Ollama
```

Details and the reasoning behind each choice: [docs/architecture.md](docs/architecture.md).

## Stack

Next.js 16 (App Router) · TypeScript · Tailwind CSS v4 · shadcn/ui-style components on Radix · TanStack Query · Zustand ·
FastAPI · Pydantic · SQLAlchemy 2 (async) · Alembic · PostgreSQL 16 · Redis · Celery · Caddy · Docker Compose ·
Monaco Editor · pytest · Vitest · Playwright. Planned: Recharts, Ollama, Qdrant/Chroma, MinIO, Prometheus, Grafana.

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
| `AI_PROVIDER`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | For SahuCodeX AI (phase 5). No model is hardcoded |
| `SANDBOX_DOCKER_HOST` | The **dedicated** Docker daemon SahuJudge runs sandboxes in — never the host's socket. Set for you in compose |
| `MAX_INFLIGHT_SUBMISSIONS`, `RATE_LIMIT_SUBMIT`, `RATE_LIMIT_RUN`, `JUDGE_STALE_AFTER` | SahuJudge abuse and cleanup limits — see [docs/judge.md](docs/judge.md) |

## Database

PostgreSQL, migrated with Alembic (`database/migrations`). Compose applies migrations on start. Manually:
`python -m alembic upgrade head` from `apps/api`. Schema and conventions: [docs/database.md](docs/database.md).

## Ollama (optional until phase 5)

```bash
docker compose --profile ai up -d ollama
docker compose exec ollama ollama pull <model-name>      # any model you like
# .env:  OLLAMA_MODEL=<model-name>
```

Or install Ollama on your host and keep `OLLAMA_BASE_URL=http://localhost:11434`. Design: [docs/ai.md](docs/ai.md).

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
[ai](docs/ai.md) (design) · [contests](docs/contests.md) (design) · [deployment](docs/deployment.md) ·
[troubleshooting](docs/troubleshooting.md)

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| **1** | Foundation: monorepo, auth, RBAC, web shell, health, migrations, Docker | **Done** |
| 2 | Problem platform: problems, tags, search/filters, Monaco editor, admin problem editor, 30 original problems | **Done** |
| 3 | SahuJudge: submissions, Redis/Celery queue, sandboxes (Python, C++, JS), verdicts, WebSocket updates | **Done** |
| 4 | Profiles, statistics, streaks, achievements, activity calendar, dashboard stats | **Done** |
| 5 | SahuCodeX AI: hints, explain, review, debug, chat, streaming, rate limits | Next |
| 6 | Contests: creation, registration, timer, scoring, penalties, live standings | |
| 7 | Community: discussions, voting, reports, notifications, moderation | |
| 8 | RAG, recommendations, caching, analytics, Prometheus/Grafana, performance | |

### Known limitations / TODO

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
* **AI Hint, AI Review and Explain remain placeholders** until phase 5.
* `POST /api/run`'s `mode=samples` (run every public example at once, capturing each one) is implemented and tested,
  but the workspace's Run button currently always uses `mode=custom` against whatever is in the input box — the
  console UI would need a second affordance to expose the samples mode.
* Only **Python, C++ and JavaScript** run; the language table (`apps/judge/sahujudge/languages.py`) is designed for
  more, but each needs a toolchain added to the runner image.
* Running more than one `judge` container needs `-B` (Celery beat, the periodic reaper) moved to exactly one replica
  — see [docs/deployment.md](docs/deployment.md#scaling-notes).

**Phase 2**

* *Format* only tidies whitespace for Python and C++ (no formatter is bundled); JavaScript uses Monaco's formatter.
* Admin covers problems and tags only. User management, contests, discussions, analytics, audit-log and health pages
  arrive with their features.
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
