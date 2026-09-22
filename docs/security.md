# Security

This page lists what is **implemented and tested today** and, separately, what is **planned**. It is kept honest on
purpose: a security document that overstates the system is worse than none.

## Implemented (phases 1 and 2)

| Area | Control | Where / how verified |
|---|---|---|
| Passwords | Argon2id, per-hash salt, transparent rehash, length bounds | `core/security.py`; `tests/test_core.py` |
| Sessions | Rotating refresh tokens, reuse detection, immediate revocation via denylist, per-device sign-out | `modules/auth/`; `tests/test_auth.py`; browser e2e |
| Token storage | Refresh token `httpOnly`, path-scoped, only its hash stored; access token in memory only | e2e asserts cookie flags and that no JWT is in web storage |
| Authorization | Server-side RBAC against the database; no roles in tokens; `extra="forbid"` on self-service input | `tests/test_authorization.py` |
| Broken access control | Users cannot escalate roles, edit others, read other users' private data or reach admin APIs | tested for USER and MODERATOR |
| Injection | SQLAlchemy parameterised queries only; `LIKE` wildcards escaped in search | `test_admin_can_list_users…` |
| XSS | Strict nonce-based CSP (no script `unsafe-inline`); React escaping; profile URLs limited to `http(s)` (and GitHub host for the GitHub field) so `javascript:`/`data:` links cannot be stored | e2e fails on any CSP violation; `test_profile_update_rejects_dangerous_…` |
| CSRF | Origin allow-list on cookie endpoints + `SameSite=Lax` | `test_refresh_rejects_cross_site_origin` |
| Open redirect | `?next=` restricted to same-site relative paths | `utils.test.ts`; e2e |
| Brute force / abuse | Redis sliding-window limits (IP, account, registration, reset, general); `Retry-After` | `tests/test_auth.py`, `tests/test_core.py` |
| IP spoofing | Only the configured number of right-most `X-Forwarded-For` hops is trusted; Caddy overwrites the header | `test_only_the_trusted_hop_is_believed`; verified against real Caddy |
| Enumeration | Uniform login error/timing; uniform forgot-password response | `test_login_failure_is_uniform_and_generic` |
| Oversized input | Body-size cap incl. chunked; bounded password length | `test_oversized_bodies_are_rejected` |
| Error hygiene | One envelope; no stack traces; validation details omit input; `/ready` hides internals | `tests/test_platform.py` |
| Headers | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, CSP (API and web), HSTS when `HTTPS_ONLY`/production, `Cache-Control: no-store` on auth routes | `tests/test_platform.py`; curl against the running stack |
| Secrets | Required `JWT_SECRET` ≥ 32 chars; production refuses placeholder secrets, insecure cookies and the console mailer; `.env` git-ignored | `test_production_refuses_unsafe_configuration` |
| Logging | Structured JSON; keys containing `password`, `token`, `secret`, `authorization`, `cookie`, or named `code` are redacted | `test_sensitive_log_fields_are_redacted` |
| Auditability | `audit_logs` for register, login, failed login, logout, session revoke, reuse detection, verification, reset | `modules/audit/` |
| Hidden tests | Public response schemas have no field that can carry them; the cached payload is built from those schemas; hints are revealed one at a time; the editorial is loaded only for solvers and admins | tests plant a sentinel in a hidden test and scan every public response for anonymous, regular and admin callers; a browser test scans every response the page receives |
| Authoring safety | Only ADMINs can create or edit problems and tests (RBAC on every route); each change is audited; publishing is validated on the server; test-case ids belonging to another problem are rejected | `tests/test_problems_admin.py` (anonymous, USER and MODERATOR against every admin route) |
| Statement rendering | Markdown without raw HTML or images; links use `noopener noreferrer`; `javascript:` links neutralised | `markdown.test.tsx` |
| Search input | `websearch_to_tsquery` on PostgreSQL never errors on hostile input; `LIKE` wildcards escaped elsewhere; filters validated on the server and sanitised on the client | search and filter tests |
| Admin body limit | The raised limit is granted only to requests bearing a token, because FastAPI reads a body before it evaluates auth | `test_admin_can_upload_large_test_files_but_others_are_capped` |
| Editor supply chain | Monaco is self-hosted, so no third-party script runs in the app origin | e2e asserts no CDN requests and no CSP violations |
| Containers | Non-root user, `cap_drop: ALL`, `no-new-privileges`, read-only root filesystem for the API, only Caddy published | `docker-compose.yml` — **not run here, see below** |
| Sandboxed code execution | Every submission and run executes inside a fresh, non-root, network-less, resource-limited, read-only-root container, torn down after; the sandbox daemon holds no application secrets and is reachable only from the judge worker over an isolated Docker network; the Docker socket is never mounted anywhere. Mandatory security tests: fork bombs, network and filesystem escape attempts, resource exhaustion, cross-submission isolation, container cleanup | `docs/judge.md`; `apps/judge/tests/test_docker_sandbox.py`, `test_docker_integration.py` (**Docker-dependent tests not run here, see below**) |
| Hidden tests during judging | A submission or run can only ever report a verdict, runtime, memory and pass counts; the pipeline populates a public test's input/output/stdout/stderr only for Run, and never for a hidden test at all — proven by planting sentinels in a hidden test and scanning every stored row and every published event | `apps/judge/tests/test_pipeline.py::test_no_hidden_data_reaches_events_or_storage`; `apps/api/tests/test_submissions_api.py` |
| Submission privacy | A submission (including its own source code) is visible only to the user who made it; another user gets the identical 404 a non-existent id would, so ids cannot be probed | `test_other_users_get_the_same_404_as_a_missing_id` |
| Judge abuse controls | Per-user rate limits on submit and run; a hard cap on submissions a user may have queued/running at once; source and custom-input size caps; a reaper closes jobs a dead worker abandoned so nothing hangs forever | `apps/api/tests/test_submissions_api.py`; `apps/judge/tests/test_pipeline.py::test_the_reaper_*` |
| Real-time events | The event WebSocket is opened only with a single-use, 30-second, server-minted ticket (stored hashed) bound to one user; a socket only ever receives that user's own channel; the Origin is checked before the ticket is even redeemed | `apps/api/tests/test_submissions_ws.py` |
| Streaks and achievements | Written only by SahuJudge after judging, never accepted from a client; the achievement catalogue seeded by the migration and the code's own `CATALOG` are cross-checked by a test so they cannot silently drift apart, and `user_achievements` is foreign-keyed to it (a bug that tried to award an unknown key would fail loudly, not silently) | `apps/api/tests/test_profiles.py`, `apps/judge/tests/test_profiles.py`, `apps/api/tests/test_migrations.py` |
| AI: hidden data | The model is only ever given a `ProblemPublic` (the public API's own shape — no field for hidden tests or the editorial), resolved server-side from a slug; the client cannot send problem text or a system prompt (`extra="forbid"`) | `apps/api/tests/test_ai.py` |
| AI: abuse and cost | Authentication on every route; one per-user Redis rate limit across all features; input, response-token and time caps; conversation and message limits; a usage row for every request, including failed and abandoned ones | `apps/api/tests/test_ai.py` |
| AI: output and privacy | Model output is rendered as inert Markdown (no raw HTML, no images, safe links) and never executed or trusted for decisions; conversations are owner-only with the same 404 for a stranger's id; the judge stays the only source of a verdict | `test_ai.py`, `assistant.test.tsx`, `markdown.test.tsx` |
| Contests: hidden problems | A contest problem is an ordinary draft (`published=False`); the plain problem API can't see it, and the contest module's own check refuses it outright before `start_time` — not a flag on the response, no field to leak | `apps/api/tests/test_contests.py` |
| Contests: scores are never client-supplied | Submit/run have no score field at all; standings are computed server-side, on every request, straight from SahuJudge's own `submissions` rows | `test_contests.py` (standings math, out-of-window submissions never counted) |
| Contests: schedule integrity | A contest's start/end time and problem list cannot change once `start_time` has passed (`409 CONTEST_ALREADY_STARTED`), server-enforced regardless of what the admin UI sends | `test_contests.py`, `contests.spec.ts` |
| Avatar URLs | Same `http(s)`-only rule as `website`/`github_url` (blocks `javascript:`/`data:`); `img-src` allows any HTTPS host since there is no upload yet and images cannot execute script | `apps/api/tests/test_authorization.py` |

## Trade-offs to be aware of

* **Account lockout is a DoS vector.** The per-account login limit (10/hour) can be triggered deliberately against a
  known username. A successful login resets it. Tighten or loosen it with `RATE_LIMIT_LOGIN_ACCOUNT`.
* **Registration reveals whether an email/username is taken.** Standard UX; mitigated by the registration rate limit.
* **Rate limiting fails open** if Redis is down (availability), while the session denylist **fails closed**
  (a revoked session must never be honoured). Redis therefore is a hard dependency for authenticated requests.
* **`style-src 'unsafe-inline'`** is required because Radix UI, Tailwind and Monaco set inline `style` attributes, and
  **`font-src data:`** because Monaco inlines its icon font as a `data:` URI. Neither permits script execution.
* **Email verification is recorded, not enforced.**
* **A user can prompt-inject their own chat** ("ignore your rules…"). The blast radius is deliberately just that user:
  the model has no tools, no database access and no other user's data — only the public problem statement and what the
  user themselves typed — and its output is inert Markdown. What the model says can never change a verdict, a score, an
  achievement or a role. The rules in the system prompt shape helpfulness; they are not a security boundary, and the
  code does not treat them as one.
* **The AI holds no secrets and the browser holds none of it**: Ollama's URL and the model name stay on the server
  (`GET /api/ai/status` returns only the model's name, to signed-in users).

## Planned (not implemented yet — do not assume)

* File uploads (avatars): size/type/name validation by content, not extension; storage abstraction (local / MinIO).
* Prometheus alerting and dependency scanning in CI.

## What has not been verified

Docker was not available in the environment where this was built, so `docker compose up`, the Dockerfiles and the
compose hardening options were **written carefully but never executed**. Everything they wrap *was* run individually:
the API against PostgreSQL 16, the migrations and seed, Next.js in production mode, a Redis-protocol server, and Caddy
with the same Caddyfile. The judge worker's pipeline was run end to end against a *trusted, test-written* sandbox
double (see [judge.md](judge.md#what-has-not-been-run-locally)) — the real Docker sandbox's isolation itself (its
mandatory security tests) was **not exercised locally**, only asserted at the level of the exact arguments it would
pass to Docker. CI runs the real Docker-backed tests on every push. Run `docker compose up --build` once, and
`SJX_DOCKER_TESTS=1 python -m pytest -m docker` in `apps/judge` once Docker is available, and use
[troubleshooting.md](troubleshooting.md) if something differs. Also: Redis was exercised through a protocol-compatible
server (`fakeredis`), not Redis itself.

## Reporting a vulnerability

Open a private security advisory on the repository, or email the maintainer. Please do not file public issues for
undisclosed vulnerabilities.
