# Community

> Status: **implemented in build phase 7**, with a completeness pass in phase 8. Per-problem discussion threads and
> replies, up/down voting, reporting, in-app notifications, and a MODERATOR-gated moderation queue — verified end to
> end, including a real registration/vote/report/moderate walkthrough.

## Rules that hold

* **A discussion belongs to exactly one problem.** There is no general/global forum — see the README's phase-7 scope
  note. `discussions.problem_id` is a required foreign key, not optional.
* **Voting is one row per (voter, target), never accumulated.** `DiscussionVote` has a
  `UNIQUE(user_id, target_type, target_id)` constraint; re-voting the same value is a no-op, switching value nets
  correctly (+1 → −1 moves the score by 2, not −2), and `target_type`/`target_id` (rather than two nullable FKs)
  lets one table cover both discussion votes and comment votes. Each target's own `vote_score` is kept denormalized
  and updated in the same transaction as the vote, so a listing page reads one integer column, never a join+`SUM`.
* **Reports never auto-remove anything.** A report only ever raises `status = OPEN`; a moderator or admin always
  makes the call (`app.modules.admin.community::resolve_report`), either `remove_content` (sets the target's
  `removed` flag — the body is replaced client-visibly, not deleted, so a thread never has a confusing gap) or
  `dismiss`.
* **Locking a thread is independent of removal.** A moderator can lock a discussion directly
  (`POST /api/moderation/discussions/{id}/lock`) without a report ever being filed — this blocks new comments
  (`409 DISCUSSION_LOCKED`) while keeping the thread and its existing comments fully visible. Unlike `removed`,
  `locked` has no report tied to it; it is a standalone moderation action, added in phase 8 after an audit found
  "remove via report" was the only moderation lever that existed (see [Known gaps closed in phase 8](#known-gaps-closed-in-phase-8)).
* **Notifications are in-app only, best-effort.** Written in the same transaction as the action that causes them (a
  reply, a removal); if that write fails the surrounding action still succeeds — a missed notification is not worth
  failing someone's comment over. No email or push.
* Every write endpoint (create a discussion, add a comment, vote, report) requires sign-in; moderation endpoints
  (the reports queue, resolve, lock/unlock) require `MODERATOR` (`ADMIN` also qualifies — `require_role` is a
  minimum-rank check), mounted under `/api/moderation`, a separate router from the plain `ADMIN`-only `/api/admin`.

## Data

`discussions`, `discussion_comments`, `discussion_votes`, `reports`, `notifications` (migration `0008`, chained
after phase 6's `0007`), plus `discussions.locked` (migration `0009`, phase 8). See
[database.md](database.md#phase-7-schema-migrations-0008-and-0009) for the full schema. No `discussion_comments` threading
(a reply is flat, not nested) — `NotificationType.COMMENT_REPLY` exists in the enum but is unused, reserved for a
future nested-reply notification that was explicitly out of scope for this phase.

## API

Public (`app.modules.community.router`, mounted at `/api`):

* `GET /discussions` — cross-problem feed (paginated), newest first, excludes discussions under unpublished problems.
* `GET /problems/{slug}/discussions`, `POST /problems/{slug}/discussions` — a problem's own thread list, and starting one.
* `GET /discussions/{id}`, `POST /discussions/{id}/comments` — a thread's detail (with its comments) and replying.
* `PUT`/`DELETE /community/{target_type}/{target_id}/vote` — cast or remove a vote (`target_type` is `discussion` or `comment`).
* `POST /community/{target_type}/{target_id}/report` — flag content for moderation.
* `GET /notifications`, `GET /notifications/unread-count`, `POST /notifications/{id}/read`, `POST /notifications/read-all`.

Moderation (`app.modules.admin.community`, mounted at `/api/moderation`, `MODERATOR`-gated):

* `GET /moderation/reports` (optional `?status=` filter), `POST /moderation/reports/{id}/resolve`.
* `POST /moderation/discussions/{id}/lock`, `POST /moderation/discussions/{id}/unlock` (phase 8).

## Frontend

`/discussions` (the cross-problem feed), a Discussion tab inside the problem statement
(`apps/web/src/components/problems/problem-statement.tsx`), `apps/web/src/components/community/` (list, thread,
notification bell), and `/moderation` (`apps/web/src/components/moderation/reports-queue.tsx`), gated client-side by
`moderation-guard.tsx` and server-side by `require_role(MODERATOR)` — the client-side gate is a courtesy, never the
real access control.

## Known gaps closed in phase 8

A completeness audit after phase 7 shipped found three real gaps, closed the same day (migration `0009` + a same-day
commit):

1. **Vote/unvote had no rate limit**, unlike every other community write (`create_discussion`, `add_comment`,
   `report` all had one). Added `rate_limit_community_vote`.
2. **The moderation reports queue did one DB fetch per report to resolve its target** (N+1 — `db.get()` in a loop).
   Now batches by target type: one query per distinct type among the page's reports, not one per report.
3. **Moderation could only remove content via a filed report** — no standalone "lock this thread" action. Added
   `discussions.locked` + the lock/unlock endpoints above (see [Rules that hold](#rules-that-hold)).

## Known limitations

* **No e2e coverage.** Every other phase has a Playwright suite (`apps/web/e2e/*.spec.ts`); community has none. Unit
  test coverage exists (22 API tests, 1 web component test for the notification bell), but no test drives a real
  browser through create-thread → reply → vote → report → moderate. This is the one carried-over gap the phase-7
  and phase-8 audits both flagged but did not close, since closing it was never part of what either phase's brief
  asked for.
* **Discussions are per-problem only** — no general/global forum, no tags, no cross-problem thread categories.
* **No nested/threaded replies** — a comment is flat under its discussion, not a reply-to-a-reply.

## Testing

22 API tests (`apps/api/tests/test_community.py`): the full discussion lifecycle (create, list, detail), comment
notifications (including that replying to your own thread never self-notifies), read/read-all, voting (up, down,
switching, repeating the same vote is a no-op, voting a comment), reporting and moderator resolution (both
`remove_content` and `dismiss`), an already-resolved report is a `409`, role gates (`MODERATOR` required, `ADMIN`
also qualifies), a removed comment's body is hidden but the row stays present, length limits, the cross-problem feed
(pagination, excludes unpublished problems), reporting/voting require auth, and the phase-8 lock/unlock behaviour
(blocks a reply with `409`, requires `MODERATOR`). Verified on SQLite and real PostgreSQL.
