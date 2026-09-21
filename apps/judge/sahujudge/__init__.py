"""SahuJudge: sandboxed compilation and execution of untrusted submissions, and deterministic verdicts.

The engine modules (`checkers`, `languages`, `sandbox`, `docker_sandbox`, `engine`) know nothing about the database
or the web framework. `pipeline` and `tasks` connect them to PostgreSQL, Redis and Celery.
"""

JUDGE_VERSION = "1"
