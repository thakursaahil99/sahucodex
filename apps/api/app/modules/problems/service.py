"""Read side of the problem platform: listing, search, filters, detail. Nothing here can return hidden tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import Float, case, cast, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import Cache
from app.core.pagination import PageParams
from app.modules.problems import search
from app.modules.problems.models import (
    Problem,
    ProblemTag,
    ProgrammingLanguage,
    ProgressStatus,
    Tag,
    UserProblemProgress,
)
from app.modules.problems.schemas import (
    ExampleOut,
    LanguageOut,
    ProblemListItem,
    ProblemPublic,
    TagOut,
    TagWithCount,
)
from app.modules.users.models import User

LANGUAGES_KEY = "problems:languages"
TAGS_KEY = "problems:tags"
DETAIL_KEY = "problem:detail:{slug}"
CACHE_TTL_SECONDS = 300

SortKey = Literal["newest", "title", "difficulty", "acceptance", "relevance"]


@dataclass
class ProblemFilters:
    q: str | None = None
    difficulties: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)  # a problem matches if it has ANY of these
    status: Literal["solved", "unsolved", "attempted"] | None = None
    min_acceptance: float | None = None
    max_acceptance: float | None = None
    sort: SortKey = "newest"


def detail_cache_key(slug: str) -> str:
    return DETAIL_KEY.format(slug=slug)


def _acceptance_expression():
    """Percentage accepted; NULL for problems nobody has submitted to yet."""
    return cast(Problem.accepted_submissions, Float) * 100.0 / func.nullif(Problem.total_submissions, 0)


def _tag_out(tag: Tag) -> TagOut:
    return TagOut(name=tag.name, slug=tag.slug)


def _visible():
    return (Problem.published.is_(True), Problem.archived_at.is_(None))


# --- Reference data -----------------------------------------------------------------------------


async def list_languages(db: AsyncSession, cache: Cache) -> list[LanguageOut]:
    cached = await cache.get_json(LANGUAGES_KEY)
    if cached is not None:
        return [LanguageOut.model_validate(item) for item in cached]
    rows = await db.scalars(
        select(ProgrammingLanguage)
        .where(ProgrammingLanguage.is_enabled.is_(True))
        .order_by(ProgrammingLanguage.sort_order)
    )
    languages = [
        LanguageOut(
            key=row.key,
            display_name=row.display_name,
            editor_language=row.editor_language,
            file_extension=row.file_extension,
        )
        for row in rows
    ]
    await cache.set_json(LANGUAGES_KEY, [lang.model_dump() for lang in languages], CACHE_TTL_SECONDS)
    return languages


async def list_tags(db: AsyncSession, cache: Cache) -> list[TagWithCount]:
    cached = await cache.get_json(TAGS_KEY)
    if cached is not None:
        return [TagWithCount.model_validate(item) for item in cached]
    stmt = (
        select(Tag, func.count(Problem.id))
        .outerjoin(ProblemTag, ProblemTag.tag_id == Tag.id)
        .outerjoin(
            Problem, (Problem.id == ProblemTag.problem_id) & Problem.published.is_(True) & Problem.archived_at.is_(None)
        )
        .group_by(Tag.id)
        .order_by(Tag.name)
    )
    tags = [TagWithCount(name=tag.name, slug=tag.slug, problem_count=count) for tag, count in await db.execute(stmt)]
    await cache.set_json(TAGS_KEY, [tag.model_dump() for tag in tags], CACHE_TTL_SECONDS)
    return tags


# --- Listing ------------------------------------------------------------------------------------


def _filtered(filters: ProblemFilters, user: User | None, dialect: str):
    stmt = select(Problem).where(*_visible())

    if filters.difficulties:
        stmt = stmt.where(Problem.difficulty.in_(filters.difficulties))
    if filters.tags:
        stmt = stmt.where(
            exists(
                select(1)
                .select_from(ProblemTag)
                .join(Tag, Tag.id == ProblemTag.tag_id)
                .where(ProblemTag.problem_id == Problem.id, Tag.slug.in_(filters.tags))
            )
        )
    if filters.status and user is not None:

        def progress(status: ProgressStatus):
            return exists(
                select(1).where(
                    UserProblemProgress.problem_id == Problem.id,
                    UserProblemProgress.user_id == user.id,
                    UserProblemProgress.status == status,
                )
            )

        if filters.status == "solved":
            stmt = stmt.where(progress(ProgressStatus.SOLVED))
        elif filters.status == "attempted":
            stmt = stmt.where(progress(ProgressStatus.ATTEMPTED))
        else:  # unsolved: never attempted, or attempted without success
            stmt = stmt.where(~progress(ProgressStatus.SOLVED))

    acceptance = _acceptance_expression()
    if filters.min_acceptance is not None:
        stmt = stmt.where(acceptance >= filters.min_acceptance)
    if filters.max_acceptance is not None:
        stmt = stmt.where(acceptance <= filters.max_acceptance)
    if filters.q:
        stmt = stmt.where(search.text_condition(filters.q, dialect))
    return stmt


def _ordered(stmt, filters: ProblemFilters, dialect: str):
    sort = filters.sort
    if sort == "relevance" and filters.q:
        rank = search.relevance(filters.q, dialect)
        if rank is not None:
            return stmt.order_by(rank.desc(), Problem.title, Problem.id)
        sort = "newest"
    if sort == "title":
        return stmt.order_by(func.lower(Problem.title), Problem.id)
    if sort == "difficulty":
        order = case({"EASY": 1, "MEDIUM": 2, "HARD": 3}, value=Problem.difficulty, else_=4)
        return stmt.order_by(order, func.lower(Problem.title), Problem.id)
    if sort == "acceptance":
        return stmt.order_by(_acceptance_expression().desc().nulls_last(), Problem.title, Problem.id)
    return stmt.order_by(Problem.published_at.desc().nulls_last(), Problem.title, Problem.id)


async def list_problems(
    db: AsyncSession, params: PageParams, filters: ProblemFilters, user: User | None
) -> tuple[list[ProblemListItem], int]:
    dialect = db.get_bind().dialect.name
    base = _filtered(filters, user, dialect)
    total = await db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    rows = list((await db.scalars(_ordered(base, filters, dialect).offset(params.offset).limit(params.limit))).unique())

    statuses: dict[uuid.UUID, str] = {}
    if user is not None and rows:
        result = await db.execute(
            select(UserProblemProgress.problem_id, UserProblemProgress.status).where(
                UserProblemProgress.user_id == user.id, UserProblemProgress.problem_id.in_([row.id for row in rows])
            )
        )
        statuses = {problem_id: status for problem_id, status in result}

    items = [
        ProblemListItem(
            slug=row.slug,
            title=row.title,
            difficulty=row.difficulty,
            tags=[_tag_out(tag) for tag in row.tags],
            acceptance_rate=row.acceptance_rate,
            total_submissions=row.total_submissions,
            status=statuses.get(row.id),
        )
        for row in rows
    ]
    return items, total


# --- Recommendations -----------------------------------------------------------------------------

_DIFFICULTY_RANK = {"EASY": 1, "MEDIUM": 2, "HARD": 3}
RECOMMENDATION_LIMIT = 10


async def recommend_problems(db: AsyncSession, user: User, limit: int = RECOMMENDATION_LIMIT) -> list[ProblemListItem]:
    """Content-based, not collaborative: no other user's behaviour is used, so there is nothing here that could leak
    who else solved what. Signal is entirely the caller's own tag history and progression:

    1. Tags of problems the caller has SOLVED, weighted by how often each tag recurs in their solves.
    2. A target difficulty: one step up from the caller's own most-solved difficulty (or EASY, solving nothing yet).
    3. Candidates are published, unarchived, and neither solved nor already attempted by the caller.

    Ranked by (tag overlap score desc, distance from the target difficulty asc, acceptance rate desc) so someone
    who mostly solves EASY array problems sees more array-tagged EASY/MEDIUM problems first, not a random HARD graph
    problem that happens to share one tag. A cold-start caller (no solves yet) gets the platform's most-accepted
    EASY problems — the least intimidating on-ramp, not an arbitrary listing order.
    """
    progress_rows = (
        await db.execute(
            select(UserProblemProgress.problem_id, UserProblemProgress.status).where(
                UserProblemProgress.user_id == user.id
            )
        )
    ).all()
    excluded_ids = {row.problem_id for row in progress_rows}
    solved_ids = [row.problem_id for row in progress_rows if row.status == ProgressStatus.SOLVED.value]

    solved_rows: list[tuple[uuid.UUID, str]] = []
    if solved_ids:
        solved_rows = (
            await db.execute(select(Problem.id, Problem.difficulty).where(Problem.id.in_(solved_ids)))
        ).all()  # fmt: skip

    if not solved_ids:
        target_difficulty = "EASY"
        tag_weights: dict[str, int] = {}
    else:
        difficulty_counts: dict[str, int] = {}
        for row in solved_rows:
            difficulty_counts[row.difficulty] = difficulty_counts.get(row.difficulty, 0) + 1
        most_solved = max(difficulty_counts, key=lambda d: difficulty_counts[d])
        target_rank = min(_DIFFICULTY_RANK[most_solved] + 1, 3)
        target_difficulty = next(d for d, r in _DIFFICULTY_RANK.items() if r == target_rank)

        tag_rows = (
            await db.execute(select(Tag.slug).join(ProblemTag, ProblemTag.tag_id == Tag.id).where(ProblemTag.problem_id.in_(solved_ids)))
        ).all()  # fmt: skip
        tag_weights = {}
        for (slug,) in tag_rows:
            tag_weights[slug] = tag_weights.get(slug, 0) + 1

    # Ranks every visible candidate in Python rather than in SQL. Fine at the problem-set sizes this platform
    # actually has (dozens, not millions) — revisit with a SQL-side score expression if the catalog grows large
    # enough for this to matter.
    candidates_stmt = select(Problem).where(*_visible())
    if excluded_ids:
        candidates_stmt = candidates_stmt.where(Problem.id.notin_(excluded_ids))
    candidates = list((await db.scalars(candidates_stmt)).unique())

    def score(problem: Problem) -> tuple[int, int, float]:
        tag_overlap = sum(tag_weights.get(tag.slug, 0) for tag in problem.tags)
        difficulty_distance = abs(_DIFFICULTY_RANK[problem.difficulty] - _DIFFICULTY_RANK[target_difficulty])
        acceptance = problem.acceptance_rate if problem.acceptance_rate is not None else 0.0
        return (-tag_overlap, difficulty_distance, -acceptance)

    ranked = sorted(candidates, key=score)[:limit]
    return [
        ProblemListItem(
            slug=p.slug,
            title=p.title,
            difficulty=p.difficulty,
            tags=[_tag_out(tag) for tag in p.tags],
            acceptance_rate=p.acceptance_rate,
            total_submissions=p.total_submissions,
            status=None,  # by construction, every candidate here is unsolved and unattempted
        )
        for p in ranked
    ]


# --- Detail -------------------------------------------------------------------------------------


def to_public(problem: Problem) -> ProblemPublic:
    """Only fields safe for everyone. Hidden test cases and the editorial are deliberately not copied."""
    return ProblemPublic(
        id=problem.id,
        slug=problem.slug,
        title=problem.title,
        difficulty=problem.difficulty,
        description=problem.description,
        constraints=problem.constraints,
        input_format=problem.input_format,
        output_format=problem.output_format,
        time_limit_ms=problem.time_limit_ms,
        memory_limit_mb=problem.memory_limit_mb,
        function_signature=problem.function_signature,
        tags=[_tag_out(tag) for tag in problem.tags],
        examples=[
            ExampleOut(
                input=example.test_case.input_data,
                output=example.test_case.expected_output,
                explanation=example.explanation,
            )
            for example in problem.examples
        ],
        hint_count=len(problem.hints or []),
        starter_code={item.language_key: item.code for item in problem.starter_codes},
        acceptance_rate=problem.acceptance_rate,
        total_submissions=problem.total_submissions,
    )


async def find_visible_problem(db: AsyncSession, slug: str) -> Problem | None:
    return await db.scalar(select(Problem).where(Problem.slug == slug, *_visible()))


async def get_public_problem(db: AsyncSession, cache: Cache, slug: str) -> ProblemPublic | None:
    cached = await cache.get_json(detail_cache_key(slug))
    if cached is not None:
        return ProblemPublic.model_validate(cached)
    problem = await find_visible_problem(db, slug)
    if problem is None:
        return None
    public = to_public(problem)
    await cache.set_json(detail_cache_key(slug), public.model_dump(mode="json"), CACHE_TTL_SECONDS)
    return public


async def progress_status(db: AsyncSession, user: User | None, problem_id: uuid.UUID) -> str | None:
    if user is None:
        return None
    return await db.scalar(
        select(UserProblemProgress.status).where(
            UserProblemProgress.user_id == user.id, UserProblemProgress.problem_id == problem_id
        )
    )
