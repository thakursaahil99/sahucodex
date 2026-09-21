"""Cleans up after failures the pipeline cannot handle itself: a worker killed mid-job, a lost message.

* Submissions stuck in QUEUED/RUNNING beyond `judge_stale_after` are closed as FAILED / SYSTEM_ERROR (not counted as
  attempts) and their owners are told, so a user is never left watching a spinner forever.
* Sandbox containers older than their self-destruct timer are removed.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update

from app.core.db import utcnow
from app.core.logging import get_logger
from app.modules.submissions import events
from app.modules.submissions.models import Submission, SubmissionStatus
from sahujudge.docker_sandbox import DockerSandbox
from sahujudge.engine import Verdict
from sahujudge.pipeline import JudgeDeps

log = get_logger(__name__)


async def fail_stale_submissions(deps: JudgeDeps) -> int:
    horizon = utcnow() - timedelta(seconds=deps.settings.judge_stale_after)
    open_states = [SubmissionStatus.QUEUED.value, SubmissionStatus.RUNNING.value]
    async with deps.sessionmaker() as db:
        stale = (
            await db.execute(
                select(Submission.id, Submission.user_id).where(
                    Submission.status.in_(open_states), Submission.created_at < horizon
                )
            )
        ).all()
        if not stale:
            return 0
        await db.execute(
            update(Submission)
            .where(Submission.id.in_([row.id for row in stale]), Submission.status.in_(open_states))
            .values(status=SubmissionStatus.FAILED.value, verdict=Verdict.SYSTEM_ERROR.value, finished_at=utcnow())
        )
        await db.commit()
    for row in stale:
        await events.publish_event(
            deps.redis,
            row.user_id,
            events.EVENT_FAILED,
            {
                "submission_id": str(row.id),
                "status": SubmissionStatus.FAILED.value,
                "verdict": Verdict.SYSTEM_ERROR.value,
                "message": "The judge did not finish this submission in time.",
            },
        )
    log.warning("stale_submissions_failed", count=len(stale))
    return len(stale)


async def reap_containers(sandbox: DockerSandbox, max_age_seconds: int) -> int:
    removed = await sandbox.reap_stale(max_age_seconds)
    if removed:
        log.warning("stale_sandbox_containers_removed", count=removed)
    return removed
