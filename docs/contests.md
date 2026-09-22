# Contests

> Status: **implemented in build phase 6.** Creation, registration, phase-gated problems, contest-scoped Run/Submit,
> and live ICPC-style standings — verified end to end, including a real registered-participant walkthrough.

## Rules that hold

* **All scoring is server-side, computed on every request, never stored.** Standings are derived straight from
  `submissions` rows tagged with a `contest_id` — the exact rows SahuJudge itself produced. There is exactly one
  place a verdict is decided and exactly one place a score is derived from it; a client-supplied score is never read
  (the submit/run endpoints don't even have a field for one).
* **Problems are hidden until the contest starts.** A contest problem is a normal, admin-authored draft
  (`Problem.published = False`) attached via `contest_problems`; the plain problem API never shows it, and the
  contest module's own visibility check (`contests/service.py::_phase`) is the only path to it — nothing at all
  before `start_time`, full content (through the same `to_public()` the plain API uses, so hidden tests and the
  editorial can't leak here any more than they can there) to anyone, registered or not, from `start_time` onward.
  Only *submitting* (or running custom input) requires registration.
* Contests are created and edited by admins only (server-enforced), and a contest's schedule and problem list cannot
  change once it has started (`409 CONTEST_ALREADY_STARTED`) — an admin cannot rug-pull problems mid-contest.
* Registering is idempotent and open any time up to `end_time`; it is what makes a submission count toward
  standings (submit/run without registering first is `403 NOT_REGISTERED`).

## Scoring model

ICPC-style, not configurable per contest beyond the point value per problem and `penalty_minutes`:

* **Problem points** — each `contest_problems` row carries a point value the admin sets.
* **Penalty time** — an accepted solution's score time is whole minutes since `start_time`, plus `penalty_minutes`
  for each earlier non-accepted *attempt* on that problem. `SYSTEM_ERROR` and `COMPILATION_ERROR` never count as an
  attempt (fixed behaviour, not a per-contest setting — this was left simpler than the original design sketch, which
  called it configurable) — the judge failing outright, or the code not even compiling, never penalises a
  participant. Every other verdict (`WRONG_ANSWER`, `TIME_LIMIT_EXCEEDED`, `MEMORY_LIMIT_EXCEEDED`,
  `RUNTIME_ERROR`) counts.
* **Ranking** — points (descending), then total penalty (ascending), then the time of the *last* accepted
  submission among solved problems (ascending) — the standard ICPC tiebreak: whoever finished scoring earlier ranks
  higher.
* A submission only counts if its `created_at` falls within `[start_time, end_time]` and its owner is a registered
  participant; every registered participant appears on the standings, even with zero solves.

## Data

`contests`, `contest_problems` and `contest_participants` (migration `0007`, chained after the
judge's own `0006_lang`), plus a nullable `contest_id` on `submissions` — see
[database.md](database.md#phase-6-schema-migration-0007). No `contest_submissions` join table and no `leaderboards`
snapshot table: a submission belongs to at most one contest, so tagging `submissions.contest_id` directly is simpler
than a join table, and standings are cheap enough to compute live that a frozen snapshot table was not worth adding.

## API

See [api.md](api.md#endpoints-implemented-so-far) for the endpoint list. The one thing worth calling out here: contest
Run and Submit reuse the exact same enqueue/event code the plain endpoints do
(`submissions/service.py::create_and_enqueue` / `run_for`) — the contest paths only change *how the problem and
language are resolved* (contest membership + timing instead of `published`), never how a job reaches SahuJudge. The
judge worker itself needed zero changes for this phase.

## Known deviations from the original design sketch

* **No `contest.started`/`contest.ending`/`contest.finished` WebSocket events.** The design doc called for these;
  building and wiring a new push channel for something the client can derive itself from `start_time`/`end_time` was
  not worth the risk this late — the frontend's `Countdown` component ticks client-side and refetches the contest
  (and so its phase) both on its own short interval and the moment the countdown reaches zero. Standings poll every
  20s while a contest is running. This trades a few seconds of staleness for not needing a new server-push
  mechanism; revisit if contests need tighter synchronisation than that.
* **No `leaderboards` snapshot table**, for the reason above (data section).
* **Penalty rules for `COMPILATION_ERROR`/`SYSTEM_ERROR` are fixed**, not the "per-contest setting" the sketch
  described — one clear, well-tested rule beat a configuration surface nothing yet needs.
* **AI assistance is switched off for contest problems** (the workspace hides the SahuCodeX AI tab entirely, not
  just its buttons) — for fairness between participants. This was not in the original sketch; it followed naturally
  once phase 5 existed to worry about.

## Testing

21 API tests (`apps/api/tests/test_contests.py`): visibility by phase, hidden-test/editorial non-leakage on the
contest problem endpoint, registration idempotency and its cutoff at `end_time`, submit/run access + contest tagging,
standings math (ranking, ICPC tiebreak, `SYSTEM_ERROR`/`COMPILATION_ERROR` never penalising, submissions outside the
contest window never counting, an in-flight/unjudged submission never counting), and admin CRUD guards (locked once
started, unknown-problem/duplicate-label/duplicate-slug rejected). Verified on SQLite and real PostgreSQL.

Frontend: unit tests for `Countdown` (a real `onReach`-fires-every-tick bug was caught here — see
[architecture.md](architecture.md)), `ContestWorkspace`, `ContestOverview` and `StandingsTable`, plus two new cases on
`ConsolePanel` for its `showAi` prop. `apps/web/e2e/contests.spec.ts` (5 tests, against a real Postgres + a real
signed-in registration/submit flow — everything except the judge verdict itself, since no Docker sandbox is
available in this environment; a submission is verified to reach `Queued` for real and to be tagged with the
contest, the same ceiling `submissions.spec.ts` already documents).
