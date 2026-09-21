# Deployment

`docker-compose.yml` is a single-host stack: Caddy, the web app, the API, PostgreSQL, Redis, the SahuJudge worker and
its dedicated sandbox Docker daemon (Ollama optional, phase 5).

## Local (development)

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:3000` (or your `WEB_PORT`). The seeded accounts from `.env.example` are available; their
passwords are development-only and documented there.

Without Docker, run the pieces yourself (this is also how the project was tested here). You need PostgreSQL and Redis
reachable at the URLs in `.env`. Then:

```bash
# 1. API (terminal 1)
cd apps/api
pip install -r requirements-dev.txt
python -m alembic upgrade head
python ../../database/seeds/run.py
python -m uvicorn app.asgi:app --reload            # http://localhost:8000/api/docs

# 2. Web (terminal 2, from the repository root)
npm install
npm run dev:web                                    # http://localhost:3000 — Next proxies /api to :8000

# 3. Judge worker (terminal 3) — needs a Docker daemon for the sandbox itself; see docs/judge.md
cd apps/judge
pip install -r requirements-dev.txt
DOCKER_HOST=... celery -A sahujudge.celery_app worker -Q judge --concurrency 2 -B
```

In this mode leave `TRUSTED_PROXY_COUNT=0` (the API then uses the socket address and ignores `X-Forwarded-For`).

**The judge worker is the one piece that cannot run without Docker somewhere**, because the sandbox *is* a Docker
container — that is the isolation mechanism (see [judge.md](judge.md)). Without step 3, or without a `SANDBOX_DOCKER_HOST`
the worker can reach, submissions and runs still enqueue normally and the API still answers, but they stay `QUEUED`
until a worker with a working sandbox daemon picks them up (the reaper eventually fails them as `SYSTEM_ERROR` rather
than leaving them stuck forever). This is why the Docker-dependent parts of SahuJudge were exercised only through
tests here, not through a running end-to-end stack — see [judge.md](judge.md#what-has-not-been-run-locally).

## Production checklist

Nothing below is optional. With `APP_ENV=production` the API refuses to start if it detects an unsafe JWT secret, the console mailer, or insecure cookies — the rest is on you.

- [ ] `APP_ENV=production`.
- [ ] A real `JWT_SECRET` (`openssl rand -hex 32`); the placeholder is rejected.
- [ ] `EMAIL_BACKEND=smtp` with a real server (the console mailer prints links and is rejected).
- [ ] `COOKIE_SECURE` unset or `true`.
- [ ] Serve over **HTTPS**: in `infrastructure/docker/Caddyfile` replace `:80` with your domain and delete
      `auto_https off` (Caddy then obtains certificates automatically); publish port 443; set `HTTPS_ONLY=true` and
      `PUBLIC_URL=https://your.domain`.
- [ ] Change **every** value marked `DEV ONLY` in `.env` (Postgres and Redis passwords especially).
- [ ] Do not seed demo users (they are skipped in production). Create the admin with a strong `SEED_ADMIN_PASSWORD`
      (≥ 12 chars) once, then remove it from `.env`.
- [ ] Remove the `127.0.0.1` port mappings for Postgres/Redis/API in `docker-compose.yml` on a shared host.
- [ ] Set `METRICS_TOKEN` if `/metrics` could ever be reached by anything other than your Prometheus.
- [ ] Set `DOCS_ENABLED=false` if you do not want the public OpenAPI page.
- [ ] Back up the `postgres-data` volume (`pg_dump` on a schedule) and test a restore.
- [ ] If another proxy or CDN sits *in front of* Caddy, tell Caddy to trust it (`servers { trusted_proxies … }`) and raise
      `TRUSTED_PROXY_COUNT` to the true number of proxies. Over-counting lets clients spoof their IP.
- [ ] **Sandbox daemon**: the bundled `sandbox` service (rootless Docker-in-Docker on the same host) is a development
      convenience. For production, run a genuinely separate, dedicated Docker host for it, point `SANDBOX_DOCKER_HOST`
      at it, and delete the `sandbox` service from `docker-compose.yml`. Never let it share a host — let alone a Docker
      daemon or socket — with anything that holds application secrets. See [judge.md](judge.md).
- [ ] **SahuCodeX AI (optional)**: run Ollama on a machine with enough RAM/GPU for your chosen model, set `OLLAMA_MODEL`
      and point the API at it (`OLLAMA_BASE_URL`; under compose, `COMPOSE_OLLAMA_URL`). Keep it off the public internet —
      it has no authentication of its own; only the API should reach it. Size `AI_REQUEST_TIMEOUT` and `RATE_LIMIT_AI`
      to your hardware: one model serves every user. Leaving `OLLAMA_MODEL` empty disables the feature cleanly.
      See [ai.md](ai.md). (The compose `ollama` service has no GPU block; add one for NVIDIA per Ollama's Docker docs.)

## Migrations and seeding

The web image's build step runs `npm run copy-monaco` (via the `prebuild` script), so the self-hosted code editor is baked
into the image; nothing is fetched from a CDN at runtime.

The API container runs `alembic upgrade head` on start (`RUN_MIGRATIONS=true` by default) and seeds when
`SEED_ON_START=true`. With more than one API replica, run migrations as a one-off job instead
(`docker compose run --rm -e RUN_MIGRATIONS=true backend true`) and set `RUN_MIGRATIONS=false` on the replicas.

## Scaling notes

**AI**: a streamed reply holds one HTTP connection open for as long as the model takes, so size your API worker count for
that; the model server itself is the throughput ceiling (Ollama queues concurrent requests). If another proxy sits in
front of the API, turn response buffering off for `text/event-stream` or replies will arrive all at once (Caddy is fine).

The API is stateless (state lives in PostgreSQL and Redis) and can be replicated behind Caddy. Rate-limit counters and
the revoked-session denylist are in Redis, so they are shared across replicas. The judge worker scales independently:
run more `judge` containers (each with `--concurrency`), but run Celery beat's periodic reaper (`-B`) on exactly **one**
of them — duplicate beats would fail the same stale submission twice, which is harmless but noisy — or run
`celery beat` as its own single replica instead. The sandbox Docker daemon is the throughput ceiling for judged code;
scale it by adding more dedicated hosts and load-balancing `SANDBOX_DOCKER_HOST` across them (nothing in the worker
assumes there is only one).
