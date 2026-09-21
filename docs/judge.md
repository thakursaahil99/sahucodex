# SahuJudge — design and implementation (phase 3)

> Status: **implemented**, verified on the hermetic test suite (108 tests: checkers, the verdict engine, the Docker
> backend's exact argument vectors, the worker pipeline against real PostgreSQL-compatible SQLite + fakeredis, and the
> full 30-problem seed catalogue judged end to end) plus 39 tests that need a real Docker daemon and were not run in
> the environment this was built in (no Docker available there — see [What has not been run locally](#what-has-not-been-run-locally)).
> CI runs all of it, including the Docker-dependent tests, on every push.

## Non-negotiable rules

1. **User code never runs in the API process, the web app, or the worker process itself.** Only inside a sandbox.
2. Each execution gets a **fresh, isolated container**, destroyed afterwards (success, failure or timeout).
3. Sandbox containers run **non-root**, **unprivileged**, with **no network**, a **read-only root filesystem**, a small
   writable `tmpfs` working directory, dropped capabilities, `no-new-privileges`, and limits on **CPU, memory, PIDs,
   wall-clock time, output size and input size**.
4. Sandboxes have **no access** to PostgreSQL, Redis, the host filesystem, environment secrets or any internal service.
5. **The Docker socket is never mounted into any container that handles user input**, and never into the API.
6. **Hidden test cases never leave the server.** Responses contain only verdict, runtime, memory, and passed/total counts.
7. The judge is **deterministic**: same problem, code, language and tests ⇒ same verdict within the configured
   environment. Runtime, memory, verdict, language and timestamp are stored.

Every rule above is asserted by a test, not just written down — see [Tests](#tests).

## The docker-socket problem, and the decision made

A worker that creates sandbox containers needs *some* way to ask a container runtime to do so. Mounting
`/var/run/docker.sock` into the worker would hand any worker compromise root on the host — unacceptable given rule 5.

**Decision: a dedicated, isolated Docker daemon (option 2 of the three considered).** `docker-compose.yml` runs a
second Docker daemon (`sandbox`, `docker:27-dind-rootless`) whose only job is running sandbox containers. It:

* has **no application data and no secrets** — it never sees `DATABASE_URL`, `REDIS_URL` or `JWT_SECRET`;
* is reachable **only** from the `judge` worker, over an **internal** Docker network (`sandbox-control`) that has no
  route to the internet, to Postgres or to Redis (the `sandbox` container is not on the application's default network
  at all, so a submission sandbox has no path to those services even if it somehow reached the daemon's host network);
* runs **rootless** (`docker:27-dind-rootless`), so a compromise of the daemon itself is a compromise of an
  unprivileged Linux user, not of the host;
* is driven by the worker through the plain `docker` CLI (`sahujudge/docker_sandbox.py`), never a client library that
  might auto-discover or fall back to the host socket.

For a real deployment with more than one host, the same worker code points `SANDBOX_DOCKER_HOST` at a genuinely
separate machine instead (optionally with `SANDBOX_RUNTIME=runsc` for gVisor), and the bundled `sandbox` service in
compose is deleted — see `.env.example`. Option 1 (a rootless/daemonless runtime driven directly, no daemon at all)
remains the natural next hardening step and needs no code change beyond the runner image and `SANDBOX_RUNTIME`;
option 3 (this decision) was chosen first because it works with a plain `docker` CLI and needs no new dependency.

The API and the queue payloads never carry secrets or code together with credentials: a payload is a bare submission
id or run id (`app/core/queue.py`). The worker loads the source from PostgreSQL (submissions) or Redis (runs) itself.

## Flow

```
Browser ──POST /api/submissions──► FastAPI: validate, size-limit, create row (QUEUED) ──► Redis queue "judge"
                                        │ returns { id } immediately (HTTP request does not wait)
                                        ▼
                              Celery judge worker (apps/judge, sahujudge.tasks.judge_submission)
                                claim QUEUED->RUNNING (atomic) ► load problem + tests ► sandbox.session()
                                ► compile ► run each test ► compare ► verdict ► save result ► publish event
                                ► sandbox torn down (finally / asyncio.shield, however the run ends)
                                        ▼
                     WebSocket (authenticated): submission.queued / running / completed / failed
```

`POST /api/run` follows the same shape (`sahujudge.tasks.run_code`) but writes to a short-lived Redis record instead
of a database row: it is not a submission, does not touch `user_problem_progress` or the problem counters, and its
mode determines what it may see — `mode=samples` runs every PUBLIC example (capturing their output, since the
statement already shows them), `mode=custom` runs the user's own input. Neither mode ever loads a HIDDEN test.

Verdicts: `ACCEPTED`, `WRONG_ANSWER`, `TIME_LIMIT_EXCEEDED`, `MEMORY_LIMIT_EXCEEDED`, `RUNTIME_ERROR`,
`COMPILATION_ERROR`, `SYSTEM_ERROR`. A crash of the judge itself — a sandbox failure, a missing problem, an unhandled
exception anywhere in `sahujudge.pipeline` — is always `SYSTEM_ERROR` and is **never counted as an attempt**
(`total_submissions`/`user_problem_progress` are untouched); a `sahujudge/reaper.py` sweep also fails any submission
left QUEUED/RUNNING past `JUDGE_STALE_AFTER` (a worker that died mid-job), on the same terms.

## Languages

Each language is a small runner configuration (`sahujudge/languages.py`: image toolchain, source filename, compile
command, run command, a time-limit multiplier for interpreted languages, a minimum container memory) — adding one is
a toolchain in `infrastructure/docker/runner/Dockerfile` plus one `LanguageSpec`, no judge logic changes. Shipped:
**Python** (×3 time multiplier), **JavaScript / Node.js** (×2), **C++17** (fixed flags: `-O2 -pipe -std=c++17`).
Designed for Java, Go, Rust, C and Kotlin later.

## The sandbox container

One container per submission (`sahujudge/docker_sandbox.py`), created and torn down around every judged submission or
run, never reused across users. `build_run_argv` — asserted by tests to be incapable of expressing a mount, a port, a
device or a privileged flag — sets:

* `--network none` — no network stack at all;
* `--read-only` root filesystem, with exactly two `tmpfs` mounts: `/work` (the source and any compiled binary; owned
  by the *unprivileged sandbox user*, mode `0700`) and `/tmp` (`noexec`); no bind mount, no volume, ever;
* `--cap-drop ALL`, `--security-opt no-new-privileges`, never `--privileged`;
* **two** unprivileged users: submitted code runs as one (uid 10001), the container's own init process — an
  in-container supervisor, `sahujudge/supervisor.py`, copied to `/opt/sjx/supervisor.py` in the runner image — runs as
  a *different* one (uid 10002), so submitted code cannot signal, ptrace, or read the memory of its own container's
  init;
* `--pids-limit`, `--memory`/`--memory-swap` (equal, so there is no swap to exhaust), `--cpus`, `--ulimit nofile`;
* `--rm`, a hard self-destruct timer on the container's main process, an explicit `docker rm --force` in a `finally`
  (shielded from cancellation, so a killed worker task still removes its container), and a periodic reaper
  (`reap_stale`, run by Celery beat every 5 minutes) for anything a hard-killed worker process left behind.

Inside the container, `supervisor.py` (stdlib only) does the actual measurement: it starts the child with `RLIMIT_CPU`/
`RLIMIT_STACK`/`RLIMIT_FSIZE`/`RLIMIT_NOFILE`/`RLIMIT_CORE`, polls `/proc/<pid>/stat` and `/status` for CPU time and
RSS, reads the container's `cgroup` `memory.events` for an OOM kill, caps stdout/stderr in memory (never touches
disk), and — however the child ends — kills every process the sandbox user owns before the next test runs. It prints
one JSON header line (status/exit code/signal/measurements) before any of the child's bytes, so a program printing
JSON that looks like a header cannot forge one; the worker treats the header as informational only — **the verdict
itself always comes from comparing the captured stdout against the expected output on the worker side**, never from
anything the supervisor or the child claims about itself.

## Output checking

`sahujudge/checkers.py`: a `Checker` protocol with `exact`, `whitespace` (any run of whitespace is one separator) and
`lines` (the default — forgives a missing trailing newline and CRLF vs LF, still cares about inner spacing, leading
whitespace, line order and blank lines in the middle) implementations, extensible via `register_checker`. Chosen per
problem (`problems.checker`, migration `0003`) and surfaced only in the admin editor.

## Result storage and hidden-test protection

Migration `0003` adds `submissions` (verdict/runtime/memory/passed·total/status — never per-test data),
`submission_results` (1:1 — compiler output, a short judge message, the checker and effective limits used) and
`submission_test_results` (one row per executed test: position, `is_public`, verdict, runtime, memory). Hidden rows
are written like any other, but:

* the submission API (`app/modules/submissions/service.py::get_submission_detail`) loads and returns only rows where
  `is_public` is true;
* `sahujudge/engine.py` only ever *populates* `input`/`expected`/`stdout`/`stderr` on a `CaseOutcome` for a PUBLIC test,
  and only when the caller explicitly asks (`capture_public=True`, used by Run; Submit never sets it) — hidden-test
  data does not reach the pipeline's own in-memory report object, let alone storage or an event;
* WebSocket/pub-sub events (`app/modules/submissions/events.py`) carry only id/status/verdict/runtime/memory/counts.

A dedicated test (`test_pipeline.py::test_no_hidden_data_reaches_events_or_storage`) plants sentinel strings in a
hidden test's input, expected output and a stderr trace that echoes the input back, judges it for real through the
pipeline, and scans every event and every database row for the sentinels.

## Mandatory security tests (`apps/judge/tests/test_docker_integration.py`)

Against a real Docker daemon and the real runner image: accepted solution (all three languages) · wrong answer ·
compilation error (and that nothing runs afterwards) · runtime error (uncaught exception, explicit exit code, SIGSEGV,
SIGABRT) · timeout (sleep, and a genuine infinite loop, both cut off promptly) · memory violation (all three
languages) · a flood of output (capped, not just slow) · a fork bomb (contained; the worker and daemon stay healthy
afterwards, proven by judging a normal submission right after) · processes left running are not visible to, or
running in, the next test · network access attempts (the internet, `postgres`/`redis` by name, raw IPs — all fail;
only the loopback interface exists) · filesystem/container escape attempts (writing outside `/work`, the Docker
socket, a host mount, `/proc/1`, another user's files, root, Linux capabilities, `no-new-privileges`, secrets in the
environment) · one submission cannot read a concurrently-running submission's source · shell metacharacters in source
are inert data, never interpreted · the sandbox container is removed when judging is cancelled · the periodic reaper
removes a container a killed worker left behind · a missing sandbox image is `SYSTEM_ERROR`, never a verdict. Each
test asserts both that the attempt failed safely (the right verdict, or the probe itself reports "blocked") **and**
that the judge stayed healthy afterwards.

## What has not been run locally

Docker was not available in the environment this was built in, so:

* the 39 tests marked `@pytest.mark.docker` (`test_docker_integration.py`) and the handful marked `@pytest.mark.linux`
  (`test_supervisor.py`'s behaviour tests, which need `/proc` and `wait4`) were **written and reviewed carefully but
  never executed locally**;
* `infrastructure/docker/runner/Dockerfile`, `infrastructure/docker/judge.Dockerfile`, and the `sandbox`/`judge`
  services added to `docker-compose.yml` were **never built or run**.

Everything they wrap *was* run: the checkers, the verdict engine, the exact `docker run`/`docker exec` argument
vectors (asserted against a scripted fake CLI, never a real daemon), the worker pipeline end to end against SQLite +
fakeredis with a trusted local sandbox double (Python the test suite itself wrote, run in a plain subprocess — no
isolation, used only to prove the pipeline's wiring), and all 30 seed problems judged through that pipeline. CI runs
the Docker-dependent tests on every push (GitHub's hosted runners ship a usable Docker Engine); run
`SJX_DOCKER_TESTS=1 python -m pytest -m docker` locally once Docker is available, and see
[troubleshooting.md](troubleshooting.md) if something differs from what CI sees.
