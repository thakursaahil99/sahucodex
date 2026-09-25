# Database

PostgreSQL 16, accessed through SQLAlchemy 2 (async, `asyncpg`). Schema changes are made **only** through Alembic
migrations in `database/migrations/versions/`.

## Conventions

* **UUID primary keys** (`uuid.uuid4()` generated in the application) for entities; a natural key where one is obvious
  (`roles.name`).
* **`timestamptz` everywhere**, always UTC. `created_at`/`updated_at` have both an application default and a
  `now()` server default.
* **Explicit constraint names** via a metadata naming convention (`pk_`, `fk_`, `uq_`, `ix_`), so migrations and
  `ALTER`s are deterministic.
* **Foreign keys with deliberate `ON DELETE` behaviour** — `CASCADE` for owned rows (profile, sessions, tokens),
  `SET NULL` for history that must outlive its actor (audit log, `granted_by`), `RESTRICT` for reference data.
* **Soft deletion** (`deleted_at`) on `users`; every lookup filters it. Hard deletes are reserved for owned child rows.
* **No enums in the database.** Values such as revoke reasons and token purposes are `VARCHAR` backed by Python
  `StrEnum`s, so adding a value never requires a migration.
* **Portable types.** `UTCDateTime` (a `TypeDecorator`) and `JSON`/`JSONB` variants let the same models run on PostgreSQL
  and on SQLite for the fast test suite.

## Phase 1 schema

```
roles ─────────────┐
 name PK           │
                   ▼
users ◄──────── user_roles (user_id, role_name) PK, granted_at, granted_by → users
 id PK
 email  UNIQUE (stored lower-case)
 username  (UNIQUE on lower(username))
 password_hash (Argon2id)
 is_active, email_verified_at, last_login_at, deleted_at
   │
   ├── 1:1  user_profiles (user_id PK/FK) avatar_url, bio, country, website, github_url
   ├── 1:N  refresh_tokens   id, user_id, family_id, token_hash UNIQUE, expires_at,
   │                         revoked_at, revoked_reason, replaced_by_id, ip_address, user_agent
   ├── 1:N  one_time_tokens  id, user_id, purpose, token_hash UNIQUE, expires_at, used_at
   └── 1:N  audit_logs       id, actor_user_id (SET NULL), action, target_*, ip, user_agent, metadata JSONB
```

Notes:

* `roles` is seeded by the migration with `USER`, `MODERATOR`, `ADMIN`.
* `uq_users_username_lower` is a functional unique index: `Sahil` and `sahil` cannot both exist. It is enforced by the
  database, not just checked in the service, so a registration race cannot create duplicates.
* Only **SHA-256 digests** of refresh and one-time tokens are stored. A database leak does not yield usable tokens.
* `refresh_tokens.family_id` is a *login session*. Rotation issues a new token in the same family; replaying an
  already-rotated token revokes the whole family.
* `audit_logs` is append-only from the application's point of view and records who/what/where — never secrets or
  request bodies.

## Phase 2 schema (migration `0002`)

```
programming_languages  key PK (python | cpp | javascript), display_name, editor_language, file_extension, is_enabled
tags                   id PK, name UNIQUE, slug UNIQUE
problems               id PK, slug UNIQUE, title, description, difficulty, constraints, input_format, output_format,
                       time_limit_ms, memory_limit_mb, editorial, hints JSONB, expected_*_complexity,
                       published, published_at, archived_at, total_submissions, accepted_submissions, created_by → users
   ├── N:M  problem_tags            (problem_id, tag_id)
   ├── 1:N  problem_test_cases      id, problem_id, kind (PUBLIC | HIDDEN), position, input_data, expected_output
   │          └── 1:1  problem_examples   test_case_id UNIQUE, position, explanation   ← a PUBLIC case shown in the statement
   └── 1:N  problem_starter_code    (problem_id, language_key) PK, code
user_problem_progress  (user_id, problem_id) PK, status (ATTEMPTED | SOLVED), attempts, first_solved_at, last_attempt_at
```

Notes:

* `problems` has `CHECK` constraints on the limits (100–10 000 ms, 16–1 024 MB): invalid limits cannot be stored even by a
  buggy caller.
* **Full-text search:** `ix_problems_fts` is a GIN index over `setweight(to_tsvector('english', title), 'A') ||
  setweight(to_tsvector('english', description), 'B')`. The query in `search.py` uses the *identical expression* so the
  planner can use the index. It is created only on PostgreSQL and listed in `MIGRATION_ONLY_INDEXES`, so the
  model-vs-migration drift test ignores it (Alembic cannot compare expression indexes reliably).
* `total_submissions` / `accepted_submissions` are denormalised counters (written by SahuJudge in phase 3), so
  acceptance-rate filtering and sorting stay an indexed read instead of an aggregate over every submission.
* Examples reference their test case (`ON DELETE CASCADE`): deleting a test removes its example, and input/output are
  never stored twice.
* Starter code, examples and test cases are updated **in place** on save. Replacing rows that share a primary or unique
  key makes SQLAlchemy INSERT before DELETE and violate the key on PostgreSQL; a regression test guards this.

## Phase 3 schema (migration `0003`)

```
problems.checker       new column: "exact" | "whitespace" | "lines" (default "lines") — which Checker judges this
                        problem's output (see docs/judge.md); set in the admin editor, never exposed publicly

submissions             id PK, user_id → users (CASCADE), problem_id → problems (CASCADE),
                        language_key → programming_languages (RESTRICT), source_code,
                        status (QUEUED | RUNNING | COMPLETED | FAILED), verdict, runtime_ms, memory_kb,
                        passed_count, total_count, created_at, started_at, finished_at
   ├── 1:1  submission_results       compile_output, message, checker, judge_version, time_limit_ms (the EFFECTIVE
   │                                 limit after the language's multiplier), memory_limit_mb
   └── 1:N  submission_test_results  position, is_public, verdict, runtime_ms, memory_kb,
                                     test_case_id → problem_test_cases (SET NULL — survives the test being edited)
```

Notes:

* `submissions.status` and `.verdict` are deliberately separate: `status` is the judge's own lifecycle (did it finish
  running?), `verdict` is the outcome. A submission the judge could not complete is `FAILED` / `SYSTEM_ERROR` and does
  **not** update `user_problem_progress` or the `problems` counters — see [judge.md](judge.md).
* `submission_test_results` never stores test input, expected output or the program's output — only a verdict and
  measurements — and the public API (`GET /api/submissions/{id}`) returns only the rows where `is_public` is true.
  `submission_results.compile_output` and `.message` are safe to return in full: they describe the *user's own* code.
* Indexes: `(user_id, created_at)` and `(user_id, problem_id, created_at)` for history pages, `(status, created_at)`
  for the stale-job reaper, `(submission_id, position)` for per-test lookups.

## Phase 4 schema (migration `0004`)

```
user_streaks       user_id PK/FK → users (CASCADE), current_streak, longest_streak, last_active_date (DATE, UTC),
                    updated_at — one row per user, created on their first ACCEPTED submission

achievements        key PK, name, description, icon (a lucide-react icon name), sort_order — seeded by the
                    migration, like `tags`/`programming_languages`; the 8 rows are fixed data, not admin-authored
   └── N:M via user_achievements  user_id → users (CASCADE), achievement_key → achievements (CASCADE),
                                  earned_at — PK (user_id, achievement_key), so an achievement is earned at most once
```

Notes:

* `last_active_date` is a **date**, not a timestamp — streaks are UTC-calendar-day granularity, so "was yesterday
  active" is a plain equality check, no timezone-sensitive range query.
* Both tables are written only by SahuJudge (`app/modules/profiles/service.py`, called from
  `sahujudge/pipeline.py` after every judged submission — see [judge.md](judge.md)), never by the client. Whether an
  achievement's *criteria* are met is evaluated in code (`app/modules/profiles/achievements.py`); the `achievements`
  table only holds what the UI needs to render one.
* The achievement catalogue exists in two places on purpose: `achievements.py`'s `CATALOG` constant (what tests seed
  and what `CHECKS` is cross-checked against) and migration `0004`'s own hardcoded copy. A migration must never import
  application code whose content could change later and silently rewrite what an old migration produces — the same
  reasoning as migration `0002`'s hardcoded language list. A test upgrades a fresh database and asserts the two
  copies still agree.
* `GET /api/users/{username}/stats` (public, like the profile itself) aggregates these two tables plus
  `user_problem_progress` (solved counts by difficulty) and `submissions` (totals, acceptance rate, and a sparse
  365-day activity calendar grouped by `date(created_at)`) — no new denormalised columns were needed.

## Phase 5 schema (migration `0005`)

```
ai_conversations   id, user_id → users (CASCADE), title (≤120), problem_slug (nullable, ≤80), created_at, updated_at
   └── 1:N ai_messages     id, conversation_id → ai_conversations (CASCADE), role ('user' | 'assistant'), content, created_at
ai_usage           id, user_id → users (CASCADE), feature ('hint' | 'explain' | 'review' | 'chat'), model,
                    conversation_id → ai_conversations (SET NULL), prompt_chars, response_chars, duration_ms, failed, created_at
```

Notes:

* `problem_slug` is a plain string, **not** a foreign key: it only labels what the chat started from and tells the server
  which *public* problem context to rebuild on each turn. An archived or renamed problem never breaks a saved
  conversation, and nothing hands the model a row to look up.
* Only the Assistant chat is stored as a transcript. Hint/Explain/Review are one-off, so they leave just an `ai_usage` row.
* `ai_usage` gets a row for every request **including failed and abandoned ones** (`failed`, `response_chars = 0`), and
  survives deleting the conversation (`SET NULL`) so cost and abuse history is not erased by the user. It is deleted with
  the user (`CASCADE`).
* Messages are ordered by `created_at`; indexes: `(user_id, created_at)` on conversations and usage,
  `(conversation_id, created_at)` on messages. Limits per user/conversation are enforced in the service, not the schema.

## Phase 6 schema (migration `0007`)

```
contests            id, slug (unique), title, description, start_time, end_time (both tz-aware), penalty_minutes,
                     published, created_by → users (SET NULL), created_at, updated_at
   └── 1:N contest_problems   id, contest_id → contests (CASCADE), problem_id → problems (RESTRICT), label
                              ("A".."Z"), points — UNIQUE(contest_id, label), UNIQUE(contest_id, problem_id)
   └── 1:N contest_participants  contest_id → contests (CASCADE), user_id → users (CASCADE), registered_at
                                 — PK (contest_id, user_id)

submissions.contest_id   nullable, → contests (SET NULL) — set only by the contest submit/run paths
```

Notes:

* Chained after `0006_lang` (the judge's added-languages migration from the same build session), not `0006` directly
  — two migrations were written concurrently; `0007` is the one that landed second and re-chained onto the other.
* `contest_problems.problem_id` is `RESTRICT`, not `CASCADE`: problems are never hard-deleted (archived instead, like
  everywhere else in the schema), so this can only ever fire as a defensive check, never in normal operation.
* `submissions.contest_id` is `SET NULL`, not `CASCADE`: a contest has no delete endpoint at all (draft or
  published, only publish/unpublish), so this is defensive too — a user's own submission history is never erased by
  a contest-side action.
* No `contest_submissions` join table: a submission belongs to at most one contest, so tagging `submissions` directly
  is simpler. No `leaderboards` snapshot table: standings are cheap enough to compute live on every request from
  `submissions` (see [contests.md](contests.md#scoring-model)) that freezing a snapshot was not worth adding.

## Phase 7 schema (migrations `0008` and `0009`)

```
discussions            id, problem_id → problems (CASCADE), author_id → users (SET NULL), title, body,
                        vote_score, comment_count, removed, locked (added in 0009), created_at, updated_at
   └── 1:N discussion_comments   id, discussion_id → discussions (CASCADE), author_id → users (SET NULL),
                                  body, vote_score, removed, created_at, updated_at

discussion_votes       id, user_id → users (CASCADE), target_type ('discussion'|'comment'), target_id, value (±1),
                        created_at — UNIQUE(user_id, target_type, target_id)

reports                id, target_type ('discussion'|'comment'), target_id, reporter_id → users (SET NULL),
                        reason, status ('OPEN'|'RESOLVED'|'DISMISSED'), resolved_by → users (SET NULL),
                        resolved_at, created_at, updated_at

notifications          id, user_id → users (CASCADE), type, data (JSON), read, created_at
```

Notes:

* `discussion_votes` and `reports` use `target_type` + `target_id` instead of two nullable foreign keys, so one
  table each covers both a discussion and a comment target without a near-duplicate table per target type.
* `discussion_comments.discussion_id` is `CASCADE`: deleting a discussion (there is no such endpoint today, but the
  constraint exists for completeness) removes its replies with it, unlike contests' deliberately defensive
  `RESTRICT`/`SET NULL` choices above — a comment has no existence independent of its thread.
* `discussions.locked` was added a phase later (`0009`), not in the original `0008` — see
  [community.md](community.md#known-gaps-closed-in-phase-8): a same-day completeness audit after phase 7 shipped
  found moderation could only remove content via a filed report, with no standalone "stop new replies" action.
* See [community.md](community.md#data) for how these are used.

## Phase 8

No new tables. RAG's data (problem embeddings) lives in Qdrant, a separate vector store, not Postgres — see
[rag.md](rag.md#setup). Recommendations and cached standings are computed from existing tables (`submissions`,
`user_problem_progress`) and a short-lived Redis cache respectively; neither needed a schema change.

## Working with migrations

```bash
cd apps/api
python -m alembic upgrade head                      # apply
python -m alembic revision --autogenerate -m "what changed"   # draft from the models, then REVIEW it
python -m alembic downgrade -1
```

Autogenerate is a starting point, not an authority. Always review the draft: for example it silently skips
expression-based indexes and emits `app.core.db.UTCDateTime`, which must be replaced with `sa.DateTime(timezone=True)`.

`tests/test_migrations.py` upgrades an empty database to `head`, then diffs the result against the models; it fails if a
model changed without a migration. It also runs `downgrade base`. Run it on PostgreSQL too:

```bash
TEST_DATABASE_URL=postgresql://user@localhost:5432/sahucodex_test python -m pytest tests/test_migrations.py
```

## Seed data

`python database/seeds/run.py` (also run on container start when `SEED_ON_START=true`). It is idempotent and reads
credentials from `SEED_*` variables — nothing secret is hardcoded. Demo users are never created when
`APP_ENV=production`, and the admin is created only if `SEED_ADMIN_PASSWORD` (≥ 12 characters) is set. It also seeds the
23 tags and the 30 original problems ([problems.md](problems.md#the-seed-catalogue)). That is content rather than
credentials, so it runs in every environment unless `SEED_PROBLEMS=false`; existing slugs are never overwritten. Phase 6
adds the sample contest.
