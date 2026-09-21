# Problem platform

Everything about problems: how they are modelled, how learners find and open them, how admins author them, and how the
30 seed problems were made trustworthy.

## Model

| Concept | Where | Notes |
|---|---|---|
| **Problem** | `problems` | Markdown `description`, `constraints`, `input_format`, `output_format`, time/memory limits, `hints` (JSON list), `editorial`, expected complexity, `published` + `archived_at` (soft delete), denormalised `total_submissions` / `accepted_submissions`. |
| **Tags** | `tags`, `problem_tags` | 23 seeded topics; admins can add more. Referenced by slug. |
| **Test case** | `problem_test_cases` | `kind` is `PUBLIC` or `HIDDEN`; stdin text in, expected stdout text out. |
| **Example** | `problem_examples` | A PUBLIC test case promoted into the statement, plus an optional explanation. It *references* the test case, so input/output live once. |
| **Starter code** | `problem_starter_code` | One row per (problem, language). Learners can only choose languages that have starter code. |
| **Languages** | `programming_languages` | Python, C++17, JavaScript (Node.js), seeded by the migration. Adding one is a data change plus a runner — see [judge.md](judge.md). |
| **Checker** | `problems.checker` | `exact` \| `whitespace` \| `lines` (default) — how SahuJudge compares a submission's output with the expected output. Set in the admin editor. |
| **Progress** | `user_problem_progress` | `ATTEMPTED` / `SOLVED` per user and problem. Written by SahuJudge on every judged submission; read by the solved/unsolved filters and to unlock editorials. |

Every problem is a **stdin → stdout program**: SahuJudge feeds a test's input to the program and compares its output
with the expected output. There is no per-language function signature to keep in sync.

### Lifecycle

```
DRAFT ──publish (validated)──► PUBLISHED ──unpublish──► DRAFT
  │                                │
  └────────────── archive ─────────┴──► ARCHIVED ──restore──► (back to its previous published state)
```

* A **draft** and an **archived** problem are invisible to the public API (`404`), immediately — caches are invalidated on
  every state change.
* **Publishing is validated on the server.** It is refused (`422 PROBLEM_NOT_READY`, with the list of blockers) unless the
  problem has: a description of at least 20 characters, input format, output format and constraints, at least one tag,
  at least one PUBLIC test shown as an example, at least **3 HIDDEN tests**, no empty expected outputs, no duplicate
  inputs, and starter code for at least one enabled language. The editor's "Check readiness" button calls
  `GET /api/admin/problems/{id}/validation`, the same checks as a dry run.

## What learners can and cannot see

| | Anonymous | Signed in | Admin |
|---|---|---|---|
| Published problem statement, examples, tags, limits, starter code | ✓ | ✓ | ✓ |
| Hints | one at a time, on request | same | same |
| Editorial + expected complexity | ✗ | only after **solving** the problem | ✓ |
| PUBLIC tests not shown as examples | ✗ | ✗ | ✓ |
| **HIDDEN tests (inputs and outputs)** | ✗ | ✗ | ✓ (admin API only) |
| Drafts and archived problems | ✗ | ✗ | ✓ |

Hidden data is kept out of public responses **by construction**: the public schemas (`ProblemPublic`, `ProblemDetail`,
`ProblemListItem`) have no field that could hold it, and the cached payload is built from those schemas. Tests assert it
at three levels — the API (a sentinel string planted in a hidden test never appears in any public response, as any
kind of user), the browser (every response the page receives is scanned), and the seeded catalogue.

## Finding problems

`GET /api/problems` (public; personalised when a token is sent):

| Parameter | Meaning |
|---|---|
| `q` | Search title, description and tag names. On PostgreSQL this is **full-text search** — stemming (`graphs` matches `graph`), ranking with the title weighted above the description, and web-search syntax (`"exact phrase"`, `-exclude`). Malformed input never errors. Other databases fall back to substring matching. |
| `difficulty` | Repeatable: `EASY`, `MEDIUM`, `HARD`. |
| `tag` | Repeatable tag slug. A problem matches if it has **any** of them. |
| `status` | `solved`, `unsolved` (never attempted *or* attempted without success) or `attempted`. Needs sign-in. |
| `min_acceptance`, `max_acceptance` | Percentages 0–100. Problems nobody has submitted to yet have no rate and are excluded when either is used. |
| `sort` | `newest` (default), `title`, `difficulty`, `acceptance`, `relevance` (needs `q`). |
| `page`, `limit` | `limit` ≤ 100. |

The web app keeps all of this in the URL, so a filtered view can be shared or reloaded, and it sanitises whatever it finds
there. The search implementation sits behind two small functions (`search.py`) — the seam for OpenSearch later.

### Caching

Redis caches the *public* part of a problem for 5 minutes, plus the tag list (with counts) and the language list. Any
admin change deletes the affected keys, so edits, unpublishing and archiving take effect at once. If Redis is down, pages
still work — they just skip the cache.

## The coding workspace

`/problems/[slug]` — statement on the left; Monaco editor, console and action bar on the right (tabs on phones).

* **Editor:** Monaco, **self-hosted** (`npm run copy-monaco` copies it to `public/monaco`; it runs automatically before
  `dev` and `build`). No CDN, so it works offline and under the Content-Security-Policy. If the bundle cannot load, a
  plain text box takes over and the draft still works.
* **Languages:** Python, C++, JavaScript. Syntax highlighting and word-based suggestions for all three; JavaScript also gets
  Monaco's TypeScript-service IntelliSense.
* **Drafts:** saved to `localStorage` automatically (debounced) and on Ctrl+S, per problem *and* language, restored on the
  next visit; "Reset" returns to the starter code after a confirmation. Font size, minimap and word wrap persist too.
* **Format:** JavaScript uses Monaco's formatter. Python and C++ have no bundled formatter, so *Format* only trims trailing
  whitespace and fixes the final newline — and says so, rather than pretending to reformat.
* **Run / Submit / AI Hint / AI Review / Explain:** present, marked unavailable, and explain which build phase delivers
  them. The console's custom-input box works; execution does not exist yet.

## Authoring (admin)

`/admin/problems` → **New problem**. A single editor with tabs: *Basics* (title, auto-slug, difficulty, limits, tags),
*Statement* (Markdown with preview, formats, constraints, complexity), *Test cases* (public/hidden, example flag +
explanation, reorder/duplicate/delete), *Starter code* (per language, with a generic template), *Hints & editorial*, and
*Publish* (readiness check, publish, unpublish, archive, restore).

* Saving sends the whole problem; test cases keep their server ids so re-saving *updates* them instead of recreating them.
* Statements are rendered as Markdown **without raw HTML or images** (no XSS, no tracking pixels); links open with
  `rel="noopener noreferrer"`.
* Every create/update/publish/archive is written to the audit log.
* Admin requests may carry bodies up to `ADMIN_MAX_REQUEST_BYTES` (8 MiB) — large hidden files — **only if they present a
  bearer token**; everyone else keeps the 1 MiB cap. Each test input/output is capped at 1 000 000 characters.

## The seed catalogue

`database/seeds/catalog/` holds **30 original problems** — 10 easy, 12 medium, 8 hard — spanning all 23 required topics.
Statements, examples, hints and editorials are original; each problem has 2 example tests and 6–10 generated hidden tests
(60 public + 250 hidden in total), starter code in three languages, and expected complexity.

How the tests can be trusted (they judge real submissions — see [judge.md](judge.md)):

1. Every problem ships a **reference solution** and a **seeded input generator**. Hidden expected outputs are *computed* by
   running the reference on the generated inputs — nothing is hand-copied. The seed is derived from the slug, so the tests
   are identical on every machine and every run.
2. A test asserts each **hand-written example output** equals the reference's output.
3. Each reference solution (all but the trivial list reversal) is **cross-checked against an independent brute force** on
   random small inputs — 150 per problem for 26 of them, plus dedicated checks for Catalan numbers (parentheses), the
   N-Queens sequence, and tree level sums.
4. Structure checks: counts by difficulty, every topic covered, unique slugs, ≥ 6 hidden tests, no duplicate inputs, sizes
   within limits, blank expected outputs rejected, starter code present (Python starters compile).
5. The seeded problems must pass the *same publish validator* an admin's problem must.

Seeding is idempotent and never overwrites: existing slugs are skipped, so admin edits survive a re-seed. Set
`SEED_PROBLEMS=false` to skip it.
