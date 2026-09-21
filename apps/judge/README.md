# SahuJudge worker (build phase 3)

Not implemented yet. This directory is reserved for the Celery judge worker that will compile and run
submissions inside isolated sandboxes. See [docs/judge.md](../../docs/judge.md) for the design and the
non-negotiable rules it will follow (no Docker socket, no network, non-root, resource limits).
