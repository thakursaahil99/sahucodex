"""Loads the seed problem catalogue into the database (idempotent)."""

from __future__ import annotations

import random
import uuid

from catalog import ALL_PROBLEMS, TAGS, Spec, slugify, starter_code
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utcnow
from app.modules.problems.models import (
    CaseKind,
    Problem,
    ProblemExample,
    ProblemStarterCode,
    ProblemTestCase,
    Tag,
)


def _normalise(output: str) -> str:
    return output.rstrip("\n") + "\n"


def build_test_inputs(spec: Spec) -> list[str]:
    """Deterministic hidden inputs: the same problem always yields the same tests."""
    return spec.hidden(random.Random(f"sahucodex:{spec.slug}"))


async def seed_problems(db: AsyncSession, *, created_by: uuid.UUID | None = None) -> tuple[int, int]:
    """Returns (created, skipped). Existing slugs are left untouched, so admin edits are never overwritten."""
    existing_tags = {tag.slug: tag for tag in await db.scalars(select(Tag))}
    for name in TAGS:
        if slugify(name) not in existing_tags:
            tag = Tag(id=uuid.uuid4(), name=name, slug=slugify(name))
            db.add(tag)
            existing_tags[tag.slug] = tag
    await db.flush()

    present = set(await db.scalars(select(Problem.slug)))
    created = skipped = 0
    for spec in ALL_PROBLEMS:
        if spec.slug in present:
            skipped += 1
            continue

        problem = Problem(
            id=uuid.uuid4(),
            slug=spec.slug,
            title=spec.title,
            description=spec.description,
            difficulty=spec.difficulty,
            constraints=spec.constraints,
            input_format=spec.input_format,
            output_format=spec.output_format,
            time_limit_ms=spec.time_limit_ms,
            memory_limit_mb=spec.memory_limit_mb,
            editorial=spec.editorial,
            hints=list(spec.hints),
            expected_time_complexity=spec.time_complexity,
            expected_space_complexity=spec.space_complexity,
            published=True,
            published_at=utcnow(),
            created_by=created_by,
        )
        problem.tags = [existing_tags[slugify(name)] for name in spec.tags]

        cases: list[ProblemTestCase] = []
        examples: list[ProblemExample] = []
        for index, example in enumerate(spec.examples):
            case = ProblemTestCase(
                id=uuid.uuid4(), kind=CaseKind.PUBLIC, position=index, input_data=example.input,
                expected_output=example.output,
            )  # fmt: skip
            cases.append(case)
            examples.append(ProblemExample(test_case=case, position=index, explanation=example.explanation))
        for offset, text in enumerate(build_test_inputs(spec)):
            cases.append(
                ProblemTestCase(
                    id=uuid.uuid4(), kind=CaseKind.HIDDEN, position=len(spec.examples) + offset, input_data=text,
                    expected_output=_normalise(spec.solve(text)),
                )  # fmt: skip
            )
        problem.test_cases = cases
        problem.examples = examples
        problem.starter_codes = [
            ProblemStarterCode(language_key=key, code=code) for key, code in starter_code(spec).items()
        ]
        db.add(problem)
        created += 1
    await db.commit()
    return created, skipped
