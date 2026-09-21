"""Write side of the problem platform. Only reachable through the ADMIN-guarded router."""

from __future__ import annotations

import re
import uuid
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import Cache
from app.core.db import utcnow
from app.core.errors import AppError, conflict, not_found
from app.core.pagination import PageParams
from app.modules.audit.service import record_audit
from app.modules.problems.models import (
    CaseKind,
    Problem,
    ProblemExample,
    ProblemStarterCode,
    ProblemTestCase,
    ProgrammingLanguage,
    Tag,
)
from app.modules.problems.schemas import (
    AdminProblemListItem,
    CaseAdminOut,
    ProblemAdminOut,
    ProblemInput,
    ValidationIssue,
)
from app.modules.problems.service import LANGUAGES_KEY, TAGS_KEY, detail_cache_key
from app.modules.users.models import User

MIN_HIDDEN_TESTS = 3
Status = Literal["DRAFT", "PUBLISHED", "ARCHIVED"]


def status_of(problem: Problem) -> Status:
    if problem.archived_at is not None:
        return "ARCHIVED"
    return "PUBLISHED" if problem.published else "DRAFT"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# --- Loading / output ---------------------------------------------------------------------------


async def load_problem(db: AsyncSession, problem_id: uuid.UUID) -> Problem:
    problem = await db.get(Problem, problem_id)
    if problem is None:
        raise not_found("PROBLEM_NOT_FOUND", "Problem not found")
    return problem


def to_admin_out(problem: Problem) -> ProblemAdminOut:
    example_by_case = {example.test_case_id: example for example in problem.examples}
    cases = []
    for case in problem.test_cases:
        example = example_by_case.get(case.id)
        cases.append(
            CaseAdminOut(
                id=case.id,
                kind=case.kind,
                input=case.input_data,
                expected_output=case.expected_output,
                show_as_example=example is not None,
                example_explanation=example.explanation if example else None,
            )
        )
    return ProblemAdminOut(
        id=problem.id,
        slug=problem.slug,
        title=problem.title,
        description=problem.description,
        difficulty=problem.difficulty,
        constraints=problem.constraints,
        input_format=problem.input_format,
        output_format=problem.output_format,
        time_limit_ms=problem.time_limit_ms,
        memory_limit_mb=problem.memory_limit_mb,
        checker=problem.checker,
        tags=[tag.slug for tag in problem.tags],
        hints=list(problem.hints or []),
        editorial=problem.editorial,
        function_signature=problem.function_signature,
        expected_time_complexity=problem.expected_time_complexity,
        expected_space_complexity=problem.expected_space_complexity,
        starter_code={item.language_key: item.code for item in problem.starter_codes},
        test_cases=cases,
        status=status_of(problem),
        published_at=problem.published_at,
        total_submissions=problem.total_submissions,
        accepted_submissions=problem.accepted_submissions,
        created_at=problem.created_at,
        updated_at=problem.updated_at,
    )


async def list_for_admin(
    db: AsyncSession, params: PageParams, q: str | None, status: Status | None
) -> tuple[list[AdminProblemListItem], int]:
    stmt = select(Problem)
    if status == "ARCHIVED":
        stmt = stmt.where(Problem.archived_at.is_not(None))
    elif status == "PUBLISHED":
        stmt = stmt.where(Problem.published.is_(True), Problem.archived_at.is_(None))
    elif status == "DRAFT":
        stmt = stmt.where(Problem.published.is_(False), Problem.archived_at.is_(None))
    if q:
        escaped = q.lower().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        pattern = f"%{escaped}%"
        stmt = stmt.where(
            or_(func.lower(Problem.title).like(pattern, escape="\\"), Problem.slug.like(pattern, escape="\\"))
        )
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = (
        await db.scalars(stmt.order_by(Problem.updated_at.desc(), Problem.id).offset(params.offset).limit(params.limit))
    ).unique()
    items = [
        AdminProblemListItem(
            id=row.id,
            slug=row.slug,
            title=row.title,
            difficulty=row.difficulty,
            status=status_of(row),
            tags=[tag.slug for tag in row.tags],
            public_tests=sum(1 for c in row.test_cases if c.kind == CaseKind.PUBLIC),
            hidden_tests=sum(1 for c in row.test_cases if c.kind == CaseKind.HIDDEN),
            total_submissions=row.total_submissions,
            updated_at=row.updated_at,
        )
        for row in rows
    ]
    return items, total


# --- Validation ---------------------------------------------------------------------------------


def validate_problem(problem: Problem, enabled_languages: set[str]) -> list[ValidationIssue]:
    """Everything that must be true before learners can see the problem."""
    issues: list[ValidationIssue] = []

    def add(field: str, code: str, message: str) -> None:
        issues.append(ValidationIssue(field=field, code=code, message=message))

    if len(problem.description.strip()) < 20:
        add("description", "DESCRIPTION_TOO_SHORT", "Write a description of at least 20 characters.")
    for field, label in (
        ("input_format", "input format"),
        ("output_format", "output format"),
        ("constraints", "constraints"),
    ):
        if not getattr(problem, field).strip():
            add(field, "REQUIRED", f"The {label} is required.")
    if not problem.tags:
        add("tags", "NO_TAGS", "Add at least one tag.")

    if not problem.examples:
        add("test_cases", "NO_EXAMPLE", "Mark at least one PUBLIC test case as a statement example.")
    hidden = [case for case in problem.test_cases if case.kind == CaseKind.HIDDEN]
    if len(hidden) < MIN_HIDDEN_TESTS:
        add("test_cases", "TOO_FEW_HIDDEN", f"Add at least {MIN_HIDDEN_TESTS} HIDDEN test cases (found {len(hidden)}).")

    seen_inputs: set[str] = set()
    for index, case in enumerate(problem.test_cases, start=1):
        if not case.expected_output.strip():
            add(f"test_cases[{index}]", "EMPTY_OUTPUT", f"Test case {index} has an empty expected output.")
        key = case.input_data.rstrip()  # leading blank lines are meaningful, trailing ones are not
        if key in seen_inputs:
            add(f"test_cases[{index}]", "DUPLICATE_TEST", f"Test case {index} repeats the input of an earlier case.")
        seen_inputs.add(key)

    if not problem.starter_codes:
        add("starter_code", "NO_STARTER_CODE", "Provide starter code for at least one language.")
    for item in problem.starter_codes:
        if item.language_key not in enabled_languages:
            add("starter_code", "UNKNOWN_LANGUAGE", f"'{item.language_key}' is not an enabled language.")
        if not item.code.strip():
            add("starter_code", "EMPTY_STARTER", f"Starter code for '{item.language_key}' is empty.")
    return issues


async def enabled_language_keys(db: AsyncSession) -> set[str]:
    return set(await db.scalars(select(ProgrammingLanguage.key).where(ProgrammingLanguage.is_enabled.is_(True))))


# --- Create / update ----------------------------------------------------------------------------


async def _resolve_tags(db: AsyncSession, slugs: list[str]) -> list[Tag]:
    if not slugs:
        return []
    found = list(await db.scalars(select(Tag).where(Tag.slug.in_(slugs))))
    missing = sorted(set(slugs) - {tag.slug for tag in found})
    if missing:
        raise AppError(422, "UNKNOWN_TAG", f"Unknown tag(s): {', '.join(missing)}", details=missing)
    return found


async def _check_slug(db: AsyncSession, slug: str, own_id: uuid.UUID | None) -> None:
    taken = await db.scalar(select(Problem.id).where(Problem.slug == slug))
    if taken is not None and taken != own_id:
        raise conflict("SLUG_TAKEN", "Another problem already uses that slug")


def _apply(problem: Problem, data: ProblemInput, tags: list[Tag], enabled: set[str]) -> None:
    unknown = sorted(set(data.starter_code) - enabled)
    if unknown:
        raise AppError(422, "UNKNOWN_LANGUAGE", f"Unknown language(s): {', '.join(unknown)}", details=unknown)

    problem.slug = data.slug
    problem.title = data.title.strip()
    problem.description = data.description
    problem.difficulty = data.difficulty
    problem.constraints = data.constraints
    problem.input_format = data.input_format
    problem.output_format = data.output_format
    problem.time_limit_ms = data.time_limit_ms
    problem.memory_limit_mb = data.memory_limit_mb
    problem.checker = data.checker
    problem.editorial = data.editorial or None
    problem.hints = data.hints
    problem.function_signature = data.function_signature or None
    problem.expected_time_complexity = data.expected_time_complexity or None
    problem.expected_space_complexity = data.expected_space_complexity or None
    problem.tags = tags

    # Everything below is updated IN PLACE where a row with the same key exists. Replacing such rows would make
    # SQLAlchemy INSERT the new one before DELETEing the old one and trip the primary/unique key.
    starters = {item.language_key: item for item in problem.starter_codes}
    for key, code in data.starter_code.items():
        starters.setdefault(key, ProblemStarterCode(language_key=key)).code = code
    problem.starter_codes = [item for key, item in starters.items() if key in data.starter_code]

    # Test cases: keep those whose id is sent back, create the rest, drop what was omitted.
    existing = {case.id: case for case in problem.test_cases}
    ordered: list[tuple[ProblemTestCase, object]] = []
    seen: set[uuid.UUID] = set()
    for position, item in enumerate(data.test_cases):
        if item.id is not None:
            case = existing.get(item.id)
            if case is None or item.id in seen:
                raise AppError(422, "UNKNOWN_TEST_CASE", "A test case id does not belong to this problem")
            seen.add(item.id)
        else:
            case = ProblemTestCase(id=uuid.uuid4())
        case.kind = item.kind
        case.position = position
        case.input_data = item.input
        case.expected_output = item.expected_output
        ordered.append((case, item))
    problem.test_cases = [case for case, _ in ordered]
    examples = {example.test_case_id: example for example in problem.examples}
    updated: list[ProblemExample] = []
    for index, (case, item) in enumerate((c, i) for c, i in ordered if i.show_as_example):
        example = examples.get(case.id) or ProblemExample(test_case=case)
        example.position = index
        example.explanation = item.example_explanation or None
        updated.append(example)
    problem.examples = updated
    problem.updated_at = utcnow()


async def _invalidate(cache: Cache, *slugs: str) -> None:
    await cache.delete(TAGS_KEY, LANGUAGES_KEY, *(detail_cache_key(slug) for slug in set(slugs)))


async def create_problem(
    db: AsyncSession, cache: Cache, admin: User, data: ProblemInput, *, ip: str, user_agent: str | None
) -> Problem:
    await _check_slug(db, data.slug, None)
    tags = await _resolve_tags(db, data.tags)
    enabled = await enabled_language_keys(db)
    problem = Problem(id=uuid.uuid4(), created_by=admin.id, published=False)
    _apply(problem, data, tags, enabled)
    db.add(problem)
    try:
        record_audit(
            db, "problem.create", actor_id=admin.id, target_type="problem", target_id=str(problem.id),
            ip=ip, user_agent=user_agent, details={"slug": data.slug},
        )  # fmt: skip
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("SLUG_TAKEN", "Another problem already uses that slug") from exc
    await _invalidate(cache, data.slug)
    return problem


async def update_problem(
    db: AsyncSession,
    cache: Cache,
    admin: User,
    problem_id: uuid.UUID,
    data: ProblemInput,
    *,
    ip: str,
    user_agent: str | None,
) -> Problem:
    problem = await load_problem(db, problem_id)
    old_slug = problem.slug
    await _check_slug(db, data.slug, problem.id)
    tags = await _resolve_tags(db, data.tags)
    enabled = await enabled_language_keys(db)
    _apply(problem, data, tags, enabled)
    try:
        record_audit(
            db, "problem.update", actor_id=admin.id, target_type="problem", target_id=str(problem.id),
            ip=ip, user_agent=user_agent, details={"slug": data.slug},
        )  # fmt: skip
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise conflict("SLUG_TAKEN", "Another problem already uses that slug") from exc
    await _invalidate(cache, old_slug, data.slug)
    return problem


Action = Literal["publish", "unpublish", "archive", "restore"]


async def change_state(
    db: AsyncSession,
    cache: Cache,
    admin: User,
    problem_id: uuid.UUID,
    action: Action,
    *,
    ip: str,
    user_agent: str | None,
) -> Problem:
    problem = await load_problem(db, problem_id)
    if action == "publish":
        if problem.archived_at is not None:
            raise conflict("PROBLEM_ARCHIVED", "Restore the problem before publishing it")
        issues = validate_problem(problem, await enabled_language_keys(db))
        if issues:
            raise AppError(
                422, "PROBLEM_NOT_READY", "The problem is not ready to publish",
                details=[issue.model_dump() for issue in issues],
            )  # fmt: skip
        problem.published = True
        problem.published_at = problem.published_at or utcnow()
    elif action == "unpublish":
        problem.published = False
    elif action == "archive":
        problem.archived_at = utcnow()
    else:
        problem.archived_at = None
    problem.updated_at = utcnow()
    record_audit(
        db, f"problem.{action}", actor_id=admin.id, target_type="problem", target_id=str(problem.id),
        ip=ip, user_agent=user_agent, details={"slug": problem.slug},
    )  # fmt: skip
    await db.commit()
    await _invalidate(cache, problem.slug)
    return problem


async def create_tag(db: AsyncSession, cache: Cache, name: str) -> Tag:
    name = name.strip()
    slug = slugify(name)
    if len(slug) < 2:
        raise AppError(422, "INVALID_TAG", "Tag names need at least two letters or digits")
    exists = await db.scalar(select(Tag.id).where(or_(Tag.slug == slug, func.lower(Tag.name) == name.lower())))
    if exists is not None:
        raise conflict("TAG_EXISTS", "That tag already exists")
    tag = Tag(id=uuid.uuid4(), name=name, slug=slug)
    db.add(tag)
    await db.commit()
    await cache.delete(TAGS_KEY)
    return tag
