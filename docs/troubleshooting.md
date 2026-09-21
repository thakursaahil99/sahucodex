# Troubleshooting

## Port 3000 is already in use

`Bind for 0.0.0.0:3000 failed` (compose) or `EADDRINUSE` (npm). Another app owns the port. Pick another and keep the two
settings in step in `.env`:

```
WEB_PORT=3100
PUBLIC_URL=http://localhost:3100
```

`PUBLIC_URL` feeds the API's CORS/CSRF allow-list; if it doesn't match what you type in the browser, login works but
token refresh fails with `403 CSRF_ORIGIN_MISMATCH`.

## The code editor doesn't load (a plain text box appears)

Monaco is served from `apps/web/public/monaco`, copied from `node_modules` by `npm run copy-monaco` (automatic before
`npm run dev` and `npm run build`). If you started the server another way, or `public/monaco` was deleted, run
`npm run copy-monaco -w @sahucodex/web` and reload. The fallback text box keeps working and still saves drafts.

## Pages hang on "Loading…" or run stale JavaScript after a rebuild

Make sure only one server is bound to the port (`EADDRINUSE` in the Next.js log) and that it was started *after* the
last build. To run a second copy of the site beside a running `next dev` (for example an end-to-end test stack), give it
its own build directory and port so neither clobbers the other:

```bash
NEXT_DIST_DIR=.next-e2e npm run build -w @sahucodex/web
cd apps/web && NEXT_DIST_DIR=.next-e2e npx next start -p 3200
```

## The problem list is empty on a fresh database

Problems come from the seed (`python database/seeds/run.py`; compose runs it on start when `SEED_ON_START=true`, unless
`SEED_PROBLEMS=false`). Only *published, non-archived* problems are public. Full-text search uses English stemming on
PostgreSQL; other databases fall back to substring matching.

## Login works, then I'm logged out immediately / redirect loop

* `403 CSRF_ORIGIN_MISMATCH` on `/api/auth/refresh` → the browser origin isn't in `CORS_ORIGINS`/`PUBLIC_URL`.
* Using HTTPS with `COOKIE_SECURE=false`, or plain HTTP with `APP_ENV=production` → the browser rejects or drops cookies.
  Use `APP_ENV=development` for plain-HTTP local runs.
* Clear cookies for the site once after changing cookie settings.

## `/ready` returns 503

The body says which dependency is `unavailable`; the reason is only in the API log
(`docker compose logs backend | grep readiness_check_failed`). Common causes: Postgres/Redis not yet healthy, wrong
`DATABASE_URL`/`REDIS_URL`, or a password containing characters that need URL-encoding (`@`, `/`, `:` — stick to
letters and digits or percent-encode).

On **Windows**, `localhost` may resolve to IPv6 `::1` first and take ~2 s to fail over, which trips the 2 s readiness
timeout when a service listens on IPv4 only. Use `127.0.0.1` in `DATABASE_URL`/`REDIS_URL` for host-run development.

## API refuses to start

The message names the setting: `JWT_SECRET must be at least 32 characters`, `placeholder value`,
`EMAIL_BACKEND=console is not allowed in production`, `COOKIE_SECURE cannot be disabled in production`. These are
deliberate safety checks (see [deployment.md](deployment.md)).

`error parsing value for field "…" from source "DotEnvSettingsSource"` → a malformed value in `.env`. Rate limits look
like `5/minute`; durations like `15m`, `7d`.

## Too many requests (`429 RATE_LIMITED`) while developing

Limits are per IP. For e2e tests or load, relax them, e.g.
`RATE_LIMIT_REGISTER=1000/minute RATE_LIMIT_LOGIN=1000/minute RATE_LIMIT_LOGIN_ACCOUNT=1000/hour`, or
`RATE_LIMIT_ENABLED=false`. To clear counters: `redis-cli --scan --pattern 'rl:*' | xargs redis-cli del`.

## Every user shares one rate-limit bucket / everyone is rate-limited together

The API sees only the proxy's address. Either there's no proxy that sets `X-Forwarded-For` (run behind Caddy as in
compose, with `TRUSTED_PROXY_COUNT=1`) or `TRUSTED_PROXY_COUNT` is `0` behind one. Do not "fix" it by trusting Next.js
rewrites — they don't add the header (see [architecture.md](architecture.md#key-decisions)).

## Verification / reset emails don't arrive

`EMAIL_BACKEND=console` prints them to the **API's stdout**, not to your inbox:
`docker compose logs backend | grep -A6 "DEV MAILBOX"`. For real delivery use `EMAIL_BACKEND=smtp`; a local
[Mailpit](https://mailpit.axllent.org/) is a good target.

## A submission or run stays "Queued" forever

Either no judge worker is running, or the worker cannot reach `SANDBOX_DOCKER_HOST`. Check
`docker compose logs judge`. If a worker was running but died mid-job, the periodic reaper closes the submission as
`SYSTEM_ERROR` after `JUDGE_STALE_AFTER` (15 minutes by default) — it is not stuck forever, just slow to notice.
Without Docker anywhere reachable, submissions and runs enqueue and sit `QUEUED` indefinitely until a worker with a
working sandbox picks them up; see [judge.md](judge.md#what-has-not-been-run-locally).

## `503 JUDGE_UNAVAILABLE` on submit or run

Redis (the broker) could not be reached when the API tried to enqueue the job. The submission is not left half-created:
it is immediately marked `FAILED` / `SYSTEM_ERROR` rather than staying `QUEUED` with nothing to pick it up.

## The judge worker logs "could not start the sandbox container"

`SANDBOX_DOCKER_HOST` does not point at a reachable, working Docker daemon. In compose, check
`docker compose logs sandbox` and its healthcheck; outside compose, confirm `DOCKER_HOST=$SANDBOX_DOCKER_HOST docker info`
succeeds from wherever the worker runs. **Never** set `SANDBOX_DOCKER_HOST` to the same daemon that runs the
application containers — see [judge.md](judge.md#the-docker-socket-problem-and-the-decision-made).

## Shell script fails in the container (`^M: bad interpreter`)

A Windows checkout converted line endings. `.gitattributes` forces LF for `*.sh`, and the API Dockerfile strips `\r`
defensively; if you still see it, re-checkout the file or run `dos2unix` on it.

## Containers won't start after pulling changes

`docker compose down` then `docker compose up --build`. To also reset the database:
`docker compose down -v` (**deletes** the Postgres and Redis volumes).

## Running the tests

```bash
cd apps/api && python -m pytest                       # hermetic: in-memory SQLite + fakeredis
TEST_DATABASE_URL=postgresql://u@localhost:5432/t python -m pytest   # same suite on real PostgreSQL
cd apps/judge && python -m pytest                      # SahuJudge: checkers, verdicts, pipeline (SQLite + fakeredis)
SJX_DOCKER_TESTS=1 python -m pytest -m docker           # + the mandatory sandbox security tests (needs Docker)
npm run test:web                                      # unit + component tests
E2E_BASE_URL=http://localhost:3000 npm run test:e2e -w @sahucodex/web   # needs the stack running + `npx playwright install chromium`
```
