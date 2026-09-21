"""Builders shared by the problem-platform tests."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI

from app.core.db import utcnow
from app.modules.problems.models import (
    CaseKind,
    Problem,
    ProblemExample,
    ProblemStarterCode,
    ProblemTestCase,
    Tag,
    UserProblemProgress,
)
from app.modules.users.models import RoleName
from tests.conftest import signed_in

HIDDEN_SENTINEL = "TOP-SECRET-HIDDEN-INPUT-7f3a"
HIDDEN_ANSWER = "TOP-SECRET-HIDDEN-ANSWER-91bc"


async def add_tags(app: FastAPI, *names: str) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    async with app.state.sessionmaker() as db:
        for name in names:
            tag = Tag(id=uuid.uuid4(), name=name, slug=name.lower().replace(" ", "-"))
            db.add(tag)
            ids[tag.slug] = tag.id
        await db.commit()
    return ids


def payload(**overrides: Any) -> dict[str, Any]:
    """A complete, publishable problem as the admin API expects it."""
    body: dict[str, Any] = {
        "title": "Harbor Cranes",
        "slug": "harbor-cranes",
        "description": "Two containers must weigh exactly the crane's capacity. Find them.",
        "difficulty": "EASY",
        "constraints": "1 <= n <= 100000",
        "input_format": "First line: n and C. Second line: n weights.",
        "output_format": "Two positions, or -1.",
        "time_limit_ms": 2000,
        "memory_limit_mb": 256,
        "tags": ["array"],
        "hints": ["Think about complements.", "A hash map remembers what you have seen."],
        "editorial": "Use a hash map from weight to index. O(n).",
        "function_signature": None,
        "expected_time_complexity": "O(n)",
        "expected_space_complexity": "O(n)",
        "starter_code": {"python": "print(-1)\n", "cpp": "int main(){}\n"},
        "test_cases": [
            {
                "kind": "PUBLIC",
                "input": "3 5\n1 4 2\n",
                "expected_output": "1 2\n",
                "show_as_example": True,
                "example_explanation": "1 + 4 = 5.",
            },
            {"kind": "HIDDEN", "input": f"3 9\n{HIDDEN_SENTINEL}\n", "expected_output": f"{HIDDEN_ANSWER}\n"},
            {"kind": "HIDDEN", "input": "2 7\n3 4\n", "expected_output": "1 2\n"},
            {"kind": "HIDDEN", "input": "1 1\n1\n", "expected_output": "-1\n"},
        ],
    }
    body.update(overrides)
    return body


async def insert_problem(
    app: FastAPI,
    slug: str,
    *,
    title: str | None = None,
    difficulty: str = "EASY",
    tags: tuple[str, ...] = (),
    published: bool = True,
    archived: bool = False,
    description: str = "A perfectly ordinary statement for testing purposes.",
    total: int = 0,
    accepted: int = 0,
    hints: tuple[str, ...] = (),
    editorial: str | None = "Editorial text",
    hidden_input: str = HIDDEN_SENTINEL,
) -> uuid.UUID:
    """Insert a problem directly (much faster than going through the admin API)."""
    async with app.state.sessionmaker() as db:
        from sqlalchemy import select

        tag_rows = list(await db.scalars(select(Tag).where(Tag.slug.in_(tags)))) if tags else []
        problem = Problem(
            id=uuid.uuid4(),
            slug=slug,
            title=title or slug.replace("-", " ").title(),
            description=description,
            difficulty=difficulty,
            constraints="n <= 10",
            input_format="a number",
            output_format="a number",
            editorial=editorial,
            hints=list(hints),
            expected_time_complexity="O(n)",
            expected_space_complexity="O(1)",
            published=published,
            published_at=utcnow() if published else None,
            archived_at=utcnow() if archived else None,
            total_submissions=total,
            accepted_submissions=accepted,
        )
        problem.tags = tag_rows
        public = ProblemTestCase(
            id=uuid.uuid4(), kind=CaseKind.PUBLIC, position=0, input_data="1\n", expected_output="2\n"
        )
        hidden = ProblemTestCase(
            id=uuid.uuid4(), kind=CaseKind.HIDDEN, position=1, input_data=hidden_input, expected_output=HIDDEN_ANSWER
        )
        problem.test_cases = [public, hidden]
        problem.examples = [ProblemExample(test_case=public, position=0, explanation="one plus one")]
        problem.starter_codes = [ProblemStarterCode(language_key="python", code="pass\n")]
        db.add(problem)
        await db.commit()
        return problem.id


async def set_progress(app: FastAPI, username: str, problem_id: uuid.UUID, status: str) -> None:
    from sqlalchemy import select

    from app.modules.users.models import User

    async with app.state.sessionmaker() as db:
        user_id = await db.scalar(select(User.id).where(User.username == username))
        db.add(UserProblemProgress(user_id=user_id, problem_id=problem_id, status=status, attempts=1))
        await db.commit()


def admin_session(app: FastAPI, username: str = "boss"):
    return signed_in(app, username=username, roles=(RoleName.ADMIN, RoleName.USER))
