# Web Preview — design (not in the 8-phase roadmap, not yet built)

> Status: **planned, not started.** This is a separate feature from SahuJudge and is not one of the platform's 8
> build phases (see the [README roadmap](../README.md#roadmap)) — it was requested afterwards. This document fixes
> the design so it can be built as its own phase (call it **Phase 9**) without redesigning SahuJudge or the judge's
> sandbox.

## Why this is not "more SahuJudge languages"

SahuJudge (see [judge.md](judge.md)) is a **competitive-programming judge**: submitted code reads one blob of text
from stdin, writes one blob of text to stdout, a sandbox process runs it to completion, and the judge diffs the
output against an expected answer. Adding a language to it (as phase 3+ did for C, Java, C#, Go, Rust, TypeScript,
PHP) means giving that language's *compiler/runtime* a stdin → stdout contract in the sandbox — nothing about the
*language itself* is special-cased.

**PHP-as-a-web-app, HTML/CSS/Ajax, Laravel and Magento are a different shape of program, not just "more languages":**

* There is no single input/output to diff. A web app **serves HTTP requests** from a **long-running process**
  (`php -S`, `php-fpm`, `artisan serve`) that stays up for as long as someone is using it — SahuJudge's model is one
  short-lived process per submission, judged and torn down in seconds.
* "Correct" has no automatic verdict. A LeetCode-style judge can diff stdout against an expected string; "does this
  Laravel app look right" is a human looking at rendered pages, not a text comparison SahuJudge can run.
* The user needs to **see and click around** the result (a browser, not a stdout blob) — this is a live preview
  product (CodeSandbox, Replit, StackBlitz), not a judge.
* Laravel and Magento are **frameworks with dependencies** (Composer packages, a database, `.env` config, in
  Magento's case a multi-minute build step) — there is no single source file to compile, and "does it run" depends
  on a project structure existing, not a snippet.

Building this well means a new sub-system alongside SahuJudge, sharing its sandbox-isolation *principles*
(deny-all network by default, no host filesystem access, hard resource limits, always destroyed) but almost none of
its *code* (`sahujudge/engine.py`, `pipeline.py`, `checkers.py` are all judge-verdict logic that has no meaning
here).

## What "Web Preview" would actually be

A **live, isolated, disposable web server for one user's project**, reachable in an iframe from the browser, for as
long as they're actively working on it — not a graded submission.

* **Input:** a small project — either a handful of files (`index.html`/`style.css`/`script.js`, or a single
  `index.php`) or, for Laravel/Magento, nothing the platform can run from scratch in seconds; see
  [Laravel and Magento](#laravel-and-magento-the-hard-case) below.
* **Where it runs:** one sandbox per session (Vercel Sandbox microVM — see [judge.md](judge.md)'s "Serverless
  backend" section for the mechanism already proven in this codebase — or a container on a host with Docker), started
  when the user opens the preview, kept alive while they're active, destroyed on an idle timeout (a fixed
  budget, e.g. 10–20 minutes, not "until they close the tab" — this is what actually bounds the cost).
* **How the browser reaches it:** the sandbox's static file server / `php -S` process is bound to a port the
  platform proxies through an authenticated URL (`vercel sandbox` supports `ports`/published routes for exactly
  this; a self-hosted container would need a reverse-proxy route per session, keyed by a signed session token so
  one user can never open another's preview).
* **What "save" means:** files live in the sandbox's disk only, gone when it's destroyed, unless the platform
  separately persists them (e.g. writing to the `problem_starter_code`-style table on an explicit Save, not on every
  keystroke).

## Laravel and Magento: the hard case

A blank Laravel project needs `composer install` (network, ~30s–2min) and usually a database. Magento needs both of
those **and** a multi-minute asset build (`bin/magento setup:upgrade`, Grunt/webpack). Neither fits "the user hits
Run and sees a page within a few seconds," which is the whole point of a preview.

The realistic options, in order of how much they cost to build and run:

1. **Pre-baked starter images.** Build one Vercel Sandbox snapshot per framework (same technique
   [judge.md](judge.md) already uses for the judge's language toolchains) with a already-`composer install`ed
   skeleton app baked in. The user edits files inside that skeleton; "Run" starts the built-in server against the
   already-installed dependencies. No live `composer install` per session. This is the only option that gives a
   fast Run for Laravel; it's what makes Magento *possible at all* within a normal request's patience, and even
   then the snapshot itself takes real time to build and maintain (framework updates mean rebuilding it).
2. **A real starting template with a live install**, accepted as slow (a minute-plus spinner) for Laravel; likely
   *not viable* for Magento even so, given its build step and typical memory needs (Magento's own docs recommend
   2 GB+ just to run, before the build) — a free-tier sandbox may not have the headroom.
3. **Static analysis only, no execution** — syntax/lint feedback on Laravel/Magento code without ever running it.
   Cheap and always available, but it is not a preview; call it what it is if this is the fallback chosen.

**Recommendation if this phase is built:** ship HTML/CSS/Ajax and plain PHP first (option requires nothing but a
static file server / `php -S`, working in the first sandbox that starts — no pre-baked image needed). Treat Laravel
as option 1 (pre-baked snapshot) as a **separate, later** milestone once the plain-PHP path is proven, and treat
Magento as *out of scope until someone explicitly asks for it and accepts the cost/latency trade-off* — it is the
most expensive item on this list by a wide margin for what is likely the least common request.

## Proposed architecture

* **New module**, not an extension of `sahujudge`: `apps/webpreview` (or `apps/api/app/modules/webpreview`, mirroring
  the judge's own API/worker split) with its own `PreviewSandbox` abstraction — deliberately *not* reusing
  `sahujudge.sandbox.Sandbox` or `RunLimits`, because "keep a server alive and proxy HTTP to it" and "run one process
  to completion and diff its output" are different enough contracts that forcing one interface over both would
  distort one of them.
* **API surface** (sketch, to be refined when this is actually built):
  * `POST /api/webpreview/sessions` — start a sandbox for a project (files, or a starter template id), returns a
    session id and its (auth-gated) preview URL.
  * `PATCH /api/webpreview/sessions/{id}/files` — write/update files in the running sandbox (what "editing and
    seeing it update" calls on each save or on a debounce).
  * `DELETE /api/webpreview/sessions/{id}` — explicit stop; also auto-expires on the idle timeout.
  * The preview URL itself is served through Caddy/Vercel routing, not through the API's own request/response
    cycle — a preview is a long-lived connection, not a single API call.
* **Isolation, same principles as the judge, independently enforced:** deny-all network (or an explicit allow-list
  if the preview needs to fetch, e.g. a CDN'd font — decide per template, default deny), no credentials or host
  paths ever passed in, the platform's own database/Redis are never reachable from inside a preview sandbox, a hard
  wall-clock session cap regardless of activity (prevents an forgotten-open tab from running forever).
* **Cost is real and ongoing**, unlike a judge submission (seconds, then gone): a preview session is billed for as
  long as it's open. This needs its own concurrency and per-user session limits, sized independently of
  `JUDGE_ENABLED`'s free-tier caps (see [judge.md](judge.md)) — the same Vercel Sandbox concurrency ceiling (10 on
  the Hobby plan) is shared with the judge, so a heavy preview session directly reduces how many judge submissions
  can run at the same time; on the free deployment these should probably not both be offered without a plan
  upgrade or a real limiter that reserves capacity for the judge.

## What this document is not

It is not an implementation plan with file-by-file steps, and no code has been written for it — see the top of this
file. It exists so that *if* this is built, it starts from a considered design (what a preview actually is, why it's
not the judge, and where the Laravel/Magento cost really lives) instead of a rushed attempt to bolt a web server onto
`sahujudge`.
