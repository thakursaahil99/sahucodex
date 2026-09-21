"""The real seed catalogue through the real pipeline (DB -> worker -> verdict -> progress).

For each of the 30 seeded problems a small *trusted* program (written here, run by the local test double) computes the
catalogue's reference answer from stdin. It must be ACCEPTED on every public and hidden test, and a program that prints
a constant must be REJECTED on every problem. Together that shows the stored tests, the default checker and the pipeline
agree, and that no test is trivially satisfiable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest_asyncio
from dbsupport import World, new_world
from sqlalchemy import func, select
from support import TrustedLocalSandbox

from app.modules.problems.models import Problem, ProblemTestCase, UserProblemProgress
from sahujudge import pipeline

SEEDS = Path(__file__).resolve().parents[3] / "database" / "seeds"
sys.path.insert(0, str(SEEDS))

from catalog import ALL_PROBLEMS  # noqa: E402
from problems_seed import seed_problems  # noqa: E402


def reference_program(slug: str) -> str:
    return (
        "import sys\n"
        f"sys.path.insert(0, {str(SEEDS)!r})\n"
        "from catalog import ALL_PROBLEMS\n"
        f"spec = next(s for s in ALL_PROBLEMS if s.slug == {slug!r})\n"
        "print(spec.solve(sys.stdin.read()))\n"
    )


@pytest_asyncio.fixture
async def seeded():
    world = await new_world(TrustedLocalSandbox(i_understand_this_runs_code_without_isolation=True))
    async with world.sessionmaker() as db:
        await seed_problems(db)
    yield world
    await world.close()


async def test_every_seeded_problem_accepts_its_reference_answer_and_rejects_a_constant(seeded: World) -> None:
    user = await seeded.add_user()
    async with seeded.sessionmaker() as db:
        problems = {slug: (pid, total) for pid, slug, total in await _problems_with_test_counts(db)}
    assert len(problems) == 30

    failures: list[str] = []
    for spec in ALL_PROBLEMS:
        problem_id, total = problems[spec.slug]
        accepted = await seeded.add_submission(user, problem_id, reference_program(spec.slug), total=total)
        verdict = await pipeline.judge_submission(seeded.deps, accepted)
        if verdict != "ACCEPTED":
            failures.append(f"{spec.slug}: reference solution got {verdict}")

        constant = await seeded.add_submission(user, problem_id, "print(0)\n", total=total)
        verdict = await pipeline.judge_submission(seeded.deps, constant)
        if verdict == "ACCEPTED":
            failures.append(f"{spec.slug}: a constant program was ACCEPTED")
    assert not failures, "\n".join(failures)

    async with seeded.sessionmaker() as db:
        rows = list(await db.scalars(select(Problem)))
        progress = list(await db.scalars(select(UserProblemProgress)))
    assert all(p.total_submissions == 2 and p.accepted_submissions == 1 for p in rows)
    assert len(progress) == 30
    assert all(p.status == "SOLVED" and p.attempts == 2 for p in progress)


async def _problems_with_test_counts(db):
    rows = await db.execute(
        select(Problem.id, Problem.slug, func.count(ProblemTestCase.id))
        .join(ProblemTestCase, ProblemTestCase.problem_id == Problem.id)
        .group_by(Problem.id, Problem.slug)
    )
    return rows.all()
