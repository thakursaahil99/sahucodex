"""Contest use cases.

Two rules everything else follows from:

* **A problem attached to a contest is never published** (`Problem.published` stays `False` the whole time it belongs
  to a contest — admins author it exactly like any other draft problem, then attach it via a contest's own
  problem list). So the plain problem API (`GET /problems`, `GET /problems/{slug}`)
  never shows it, and the ONLY way to reach it is through this module's own visibility rule (`_phase`,
  `get_contest_problem`): nothing at all before `start_time`, full content from `start_time` onward, for anyone
  (spectators too — only *submitting* requires registration).
* **Standings are computed, never stored.** They are derived, on every request, straight from `submissions` rows that
  carry this contest's id — the exact same rows SahuJudge already produced. There is no second place a score could
  drift from the judge's own verdict.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import utcnow
from app.core.errors import AppError, conflict, not_found
from app.modules.contests.models import Contest, ContestParticipant, ContestProblem
from app.modules.contests.schemas import (
    ContestAdminInput,
    ContestAdminOut,
    ContestAdminProblemOut,
    ContestDetail,
    ContestListItem,
    ContestPhase,
    ContestProblemOut,
    ContestProblemRef,
    StandingsCell,
    StandingsOut,
    StandingsRow,
)
from app.modules.problems import service as problems
from app.modules.problems.models import Problem
from app.modules.submissions.models import Submission, SubmissionStatus, Verdict
from app.modules.submissions.service import ProblemRef, resolve_language
from app.modules.users.models import User

# Verdicts that never count as an attempt: the judge could not evaluate the code at all, so nothing about the
# participant's *solution* was tested. Every other verdict (WRONG_ANSWER, TLE, MLE, RUNTIME_ERROR) counts.
_NOT_AN_ATTEMPT = {Verdict.SYSTEM_ERROR.value, Verdict.COMPILATION_ERROR.value}


def _phase(contest: Contest, now: datetime) -> ContestPhase:
    if now < contest.start_time:
        return "upcoming"
    if now <= contest.end_time:
        return "running"
    return "ended"


def _visible():
    return (Contest.published.is_(True),)


async def _find(db: AsyncSession, slug: str) -> Contest | None:
    return await db.scalar(select(Contest).where(Contest.slug == slug, *_visible()))


async def get_contest(db: AsyncSession, slug: str) -> Contest:
    contest = await _find(db, slug)
    if contest is None:
        raise not_found("CONTEST_NOT_FOUND", "Contest not found")
    return contest


async def list_contests(db: AsyncSession) -> list[ContestListItem]:
    rows = await db.scalars(select(Contest).where(*_visible()).order_by(Contest.start_time.desc()))
    now = utcnow()
    return [
        ContestListItem(
            slug=c.slug,
            title=c.title,
            start_time=c.start_time,
            end_time=c.end_time,
            phase=_phase(c, now),
            problem_count=len(c.problems),
        )
        for c in rows
    ]


async def _is_registered(db: AsyncSession, contest_id: uuid.UUID, user: User | None) -> bool:
    if user is None:
        return False
    return (
        await db.scalar(
            select(ContestParticipant).where(
                ContestParticipant.contest_id == contest_id, ContestParticipant.user_id == user.id
            )
        )
    ) is not None


async def get_contest_detail(db: AsyncSession, slug: str, user: User | None) -> ContestDetail:
    contest = await get_contest(db, slug)
    now = utcnow()
    phase = _phase(contest, now)
    # Titles cost a second query, so only pay for it once a contest has actually started; before that, no problem
    # information beyond the point value and label is ever sent.
    titles = await _titles_for(db, contest) if phase != "upcoming" else {}
    return ContestDetail(
        slug=contest.slug,
        title=contest.title,
        start_time=contest.start_time,
        end_time=contest.end_time,
        phase=phase,
        problem_count=len(contest.problems),
        description=contest.description,
        penalty_minutes=contest.penalty_minutes,
        problems=[
            ContestProblemRef(label=p.label, points=p.points, title=titles[p.problem_id][1] if titles else None)
            for p in contest.problems
        ],
        registered=await _is_registered(db, contest.id, user),
    )


async def register(db: AsyncSession, slug: str, user: User) -> None:
    contest = await get_contest(db, slug)
    if utcnow() > contest.end_time:
        raise conflict("CONTEST_ENDED", "This contest has already ended")
    if await _is_registered(db, contest.id, user):
        return  # idempotent: registering twice is a no-op, not an error
    db.add(ContestParticipant(contest_id=contest.id, user_id=user.id, registered_at=utcnow()))
    await db.commit()


async def _find_contest_problem(db: AsyncSession, contest: Contest, label: str) -> ContestProblem:
    for p in contest.problems:
        if p.label == label:
            return p
    raise not_found("CONTEST_PROBLEM_NOT_FOUND", "No such problem in this contest")


async def get_contest_problem(db: AsyncSession, slug: str, label: str) -> ContestProblemOut:
    contest = await get_contest(db, slug)
    if _phase(contest, utcnow()) == "upcoming":
        raise not_found("CONTEST_PROBLEM_NOT_FOUND", "No such problem in this contest")
    contest_problem = await _find_contest_problem(db, contest, label)
    problem = await db.get(Problem, contest_problem.problem_id)
    assert problem is not None  # RESTRICT on delete: a contest_problems row always has a live problem
    return ContestProblemOut(
        label=contest_problem.label, points=contest_problem.points, problem=problems.to_public(problem)
    )


async def resolve_contest_submission(
    db: AsyncSession, slug: str, label: str, user: User, language: str
) -> tuple[Contest, ProblemRef, str]:
    """Validates contest timing + registration + the problem's membership, and resolves problem/language the same
    way the plain submit path does. Returns (contest, ProblemRef, language_key) for `create_and_enqueue`/`run_for` —
    shared by both the submit and the run (custom-input test) endpoints; testing your code needs the same access a
    submission does, nothing looser."""
    contest = await get_contest(db, slug)
    phase = _phase(contest, utcnow())
    if phase == "upcoming":
        raise not_found("CONTEST_PROBLEM_NOT_FOUND", "No such problem in this contest")
    if phase == "ended":
        raise conflict("CONTEST_ENDED", "This contest has ended; submissions are no longer accepted")
    if not await _is_registered(db, contest.id, user):
        raise AppError(403, "NOT_REGISTERED", "Register for this contest before submitting")

    contest_problem = await _find_contest_problem(db, contest, label)
    problem = await db.get(Problem, contest_problem.problem_id)
    assert problem is not None
    language_key = await resolve_language(db, language)
    problem_ref = ProblemRef(
        id=problem.id, slug=problem.slug, title=problem.title,
        time_limit_ms=problem.time_limit_ms, memory_limit_mb=problem.memory_limit_mb,
    )  # fmt: skip
    return contest, problem_ref, language_key


# --- standings -----------------------------------------------------------------------------------------------------


@dataclass
class _Attempt:
    accepted: bool
    counts: bool  # False for SYSTEM_ERROR/COMPILATION_ERROR — never an attempt, never a penalty
    created_at: datetime


async def compute_standings(db: AsyncSession, contest: Contest) -> StandingsOut:
    participants = (
        await db.execute(
            select(ContestParticipant.user_id, User.username)
            .join(User, User.id == ContestParticipant.user_id)
            .where(ContestParticipant.contest_id == contest.id)
        )
    ).all()

    submissions = (
        await db.execute(
            select(
                Submission.user_id, Submission.problem_id, Submission.status, Submission.verdict, Submission.created_at
            )
            .where(
                Submission.contest_id == contest.id,
                Submission.created_at >= contest.start_time,
                Submission.created_at <= contest.end_time,
            )
            .order_by(Submission.created_at)
        )
    ).all()  # fmt: skip

    by_pair: dict[tuple[uuid.UUID, uuid.UUID], list[_Attempt]] = defaultdict(list)
    for user_id, problem_id, status, verdict, created_at in submissions:
        if status != SubmissionStatus.COMPLETED.value or verdict is None:
            continue  # still judging, or the judge itself failed outright (FAILED) — neither is a scored attempt
        by_pair[(user_id, problem_id)].append(
            _Attempt(
                accepted=verdict == Verdict.ACCEPTED.value, counts=verdict not in _NOT_AN_ATTEMPT, created_at=created_at
            )
        )

    # A plain (non-Pydantic) intermediate so the tiebreak key can ride along for sorting without being part of the
    # response shape — StandingsRow only ever holds fields the API actually returns. Tiebreak (standard ICPC rule):
    # among equal points and penalty, whoever's LAST accepted submission came earliest ranks higher. `nothing_yet`
    # (the lowest possible timestamp) as the "solved nothing" starting value never wrongly outranks an actual
    # solver, because total_points (the primary key) already separates them; it only ties two 0-point rows together,
    # which is the correct, harmless outcome.
    nothing_yet = datetime.min.replace(tzinfo=contest.start_time.tzinfo)
    computed: list[tuple[datetime, StandingsRow]] = []
    for user_id, username in participants:
        cells: dict[str, StandingsCell] = {}
        total_points = 0
        total_penalty = 0
        last_accepted = nothing_yet
        for cp in contest.problems:
            attempts = by_pair.get((user_id, cp.problem_id), [])
            wrong_before = 0
            solved_at: datetime | None = None
            for attempt in attempts:  # already ordered by created_at
                if attempt.accepted:
                    solved_at = attempt.created_at
                    break
                if attempt.counts:
                    wrong_before += 1
            if solved_at is not None:
                minutes = int((solved_at - contest.start_time).total_seconds() // 60)
                penalty = minutes + wrong_before * contest.penalty_minutes
                cells[cp.label] = StandingsCell(solved=True, attempts=wrong_before, penalty_minutes=penalty)
                total_points += cp.points
                total_penalty += penalty
                last_accepted = max(last_accepted, solved_at)
            else:
                total_attempts = sum(1 for a in attempts if a.counts)
                cells[cp.label] = StandingsCell(solved=False, attempts=total_attempts, penalty_minutes=0)
        row = StandingsRow(
            rank=0, username=username, total_points=total_points, total_penalty_minutes=total_penalty, cells=cells
        )
        computed.append((last_accepted, row))

    computed.sort(key=lambda item: (-item[1].total_points, item[1].total_penalty_minutes, item[0]))
    rows = [row for _, row in computed]
    for i, row in enumerate(rows, start=1):
        row.rank = i

    return StandingsOut(
        generated_at=utcnow(),
        problems=[ContestProblemRef(label=p.label, points=p.points, title=None) for p in contest.problems],
        rows=rows,
    )


# --- admin ----------------------------------------------------------------------------------------------------------


def _admin_out(contest: Contest, titles: dict[uuid.UUID, str]) -> ContestAdminOut:
    return ContestAdminOut(
        id=contest.id,
        slug=contest.slug,
        title=contest.title,
        description=contest.description,
        start_time=contest.start_time,
        end_time=contest.end_time,
        penalty_minutes=contest.penalty_minutes,
        published=contest.published,
        problems=[
            ContestAdminProblemOut(
                label=p.label,
                points=p.points,
                problem_slug=titles[p.problem_id][0],
                problem_title=titles[p.problem_id][1],
            )
            for p in contest.problems
        ],
        created_at=contest.created_at,
        updated_at=contest.updated_at,
    )


async def _titles_for(db: AsyncSession, contest: Contest) -> dict[uuid.UUID, tuple[str, str]]:
    if not contest.problems:
        return {}
    ids = [p.problem_id for p in contest.problems]
    rows = (await db.execute(select(Problem.id, Problem.slug, Problem.title).where(Problem.id.in_(ids)))).all()
    return {pid: (slug, title) for pid, slug, title in rows}


async def list_for_admin(db: AsyncSession) -> list[ContestAdminOut]:
    rows = (await db.scalars(select(Contest).order_by(Contest.start_time.desc()))).all()
    out = []
    for contest in rows:
        out.append(_admin_out(contest, await _titles_for(db, contest)))
    return out


async def get_for_admin(db: AsyncSession, contest_id: uuid.UUID) -> ContestAdminOut:
    contest = await db.get(Contest, contest_id)
    if contest is None:
        raise not_found("CONTEST_NOT_FOUND", "Contest not found")
    return _admin_out(contest, await _titles_for(db, contest))


async def _check_slug(db: AsyncSession, slug: str, own_id: uuid.UUID | None) -> None:
    existing = await db.scalar(select(Contest.id).where(Contest.slug == slug))
    if existing is not None and existing != own_id:
        raise conflict("SLUG_TAKEN", "A contest with this slug already exists")


async def _resolve_problems(db: AsyncSession, data: ContestAdminInput) -> list[tuple[Problem, str, int]]:
    resolved = []
    for item in data.problems:
        problem = await db.scalar(
            select(Problem).where(Problem.slug == item.problem_slug, Problem.archived_at.is_(None))
        )
        if problem is None:
            raise AppError(422, "PROBLEM_NOT_FOUND", f"No problem with slug '{item.problem_slug}'")
        resolved.append((problem, item.label, item.points))
    return resolved


def _guard_not_started(contest: Contest) -> None:
    if utcnow() >= contest.start_time:
        raise conflict("CONTEST_ALREADY_STARTED", "A contest's schedule and problems cannot change once it has started")


async def create_contest(db: AsyncSession, admin: User, data: ContestAdminInput) -> ContestAdminOut:
    await _check_slug(db, data.slug, None)
    resolved = await _resolve_problems(db, data)
    contest = Contest(
        id=uuid.uuid4(),
        slug=data.slug,
        title=data.title,
        description=data.description,
        start_time=data.start_time,
        end_time=data.end_time,
        penalty_minutes=data.penalty_minutes,
        created_by=admin.id,
        published=False,
    )
    contest.problems = [
        ContestProblem(id=uuid.uuid4(), problem_id=problem.id, label=label, points=points)
        for problem, label, points in resolved
    ]
    db.add(contest)
    await db.commit()
    return _admin_out(contest, await _titles_for(db, contest))


async def update_contest(db: AsyncSession, contest_id: uuid.UUID, data: ContestAdminInput) -> ContestAdminOut:
    contest = await db.scalar(select(Contest).where(Contest.id == contest_id).options(selectinload(Contest.problems)))
    if contest is None:
        raise not_found("CONTEST_NOT_FOUND", "Contest not found")
    _guard_not_started(contest)
    await _check_slug(db, data.slug, contest.id)
    resolved = await _resolve_problems(db, data)

    contest.slug = data.slug
    contest.title = data.title
    contest.description = data.description
    contest.start_time = data.start_time
    contest.end_time = data.end_time
    contest.penalty_minutes = data.penalty_minutes
    # Flush the deletion of the old rows before inserting the new ones: `contest_problems` has a UNIQUE(contest_id,
    # problem_id), and keeping the same problem across an edit means an old and a new row can share that pair —
    # letting the ORM order delete-orphan and insert within one flush risks doing the insert first and violating it.
    contest.problems = []
    await db.flush()
    contest.problems = [
        ContestProblem(id=uuid.uuid4(), problem_id=problem.id, label=label, points=points)
        for problem, label, points in resolved
    ]
    await db.commit()
    return _admin_out(contest, await _titles_for(db, contest))


async def set_published(db: AsyncSession, contest_id: uuid.UUID, published: bool) -> ContestAdminOut:
    contest = await db.get(Contest, contest_id)
    if contest is None:
        raise not_found("CONTEST_NOT_FOUND", "Contest not found")
    if published and not contest.problems:
        raise AppError(422, "CONTEST_NOT_READY", "Add at least one problem before publishing")
    contest.published = published
    await db.commit()
    return _admin_out(contest, await _titles_for(db, contest))
