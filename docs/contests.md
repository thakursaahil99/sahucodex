# Contests — design (build phase 6, not yet implemented)

> Status: **planned.** Nothing here exists yet.

## Rules that will hold

* **All scoring is server-side.** Clients submit code; the server judges it and computes points, penalties and rank.
  Client-supplied scores are never read.
* **Problems are hidden until the contest starts.** The API refuses contest problem access before `start_time` — the
  check lives in the query/service layer, not the UI.
* Contests are created and edited by admins only (server-enforced).
* Contest events (`contest.started`, `contest.ending`, `contest.finished`) are pushed over the authenticated WebSocket.

## Scoring model (configurable per contest)

* **Problem points** — each problem carries a point value.
* **Penalty time** — an accepted solution's score time is the minutes since contest start plus a fixed penalty per prior
  wrong attempt on that problem (ICPC-style), only for problems eventually solved.
* **Ranking** — points (descending), then total penalty (ascending), then time of last accepted submission.
* Only verdicts that count (`ACCEPTED`, and wrong-answer-like verdicts as attempts) affect standings; `COMPILATION_ERROR`
  and `SYSTEM_ERROR` handling is a per-contest setting, and `SYSTEM_ERROR` never penalises a participant.

## Data

`contests`, `contest_problems`, `contest_participants`, `contest_submissions`, `leaderboards` (snapshots), as listed in
[database.md](database.md#planned-tables). Live standings are computed from `contest_submissions` and cached in Redis
with explicit invalidation on each judged submission; the final standings are frozen into `leaderboards` at the end.
