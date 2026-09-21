"""Problem text search.

PostgreSQL uses full-text search (stemming, ranking, `websearch` syntax) backed by the GIN index created in
migration 0002. Other dialects (SQLite in the fast test suite) fall back to substring matching.

Keeping this behind two small functions is the seam for a dedicated engine later: swapping in OpenSearch means
replacing `text_condition` / `relevance` with a lookup that returns matching problem ids, nothing else changes.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, String, bindparam, exists, func, literal_column, or_, select

from app.modules.problems.models import Problem, ProblemTag, Tag

# Same expression as ix_problems_fts in migration 0002 (there unqualified, here table-qualified).
_DOCUMENT = (
    "setweight(to_tsvector('english'::regconfig, coalesce(problems.title, '')), 'A') || "
    "setweight(to_tsvector('english'::regconfig, coalesce(problems.description, '')), 'B')"
)
_CONFIG = "'english'::regconfig"


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


def _tag_matches(pattern: str) -> ColumnElement[bool]:
    return exists(
        select(1)
        .select_from(ProblemTag)
        .join(Tag, Tag.id == ProblemTag.tag_id)
        .where(ProblemTag.problem_id == Problem.id, func.lower(Tag.name).like(pattern, escape="\\"))
    )


def _tsquery(query: str, name: str) -> ColumnElement:
    return func.websearch_to_tsquery(literal_column(_CONFIG), bindparam(name, query, type_=String()))


def text_condition(query: str, dialect: str) -> ColumnElement[bool]:
    """Title, description or tag matches `query`."""
    pattern = f"%{_escape_like(query.lower())}%"
    if dialect == "postgresql":
        document = literal_column(f"({_DOCUMENT})")
        return or_(document.op("@@")(_tsquery(query, "fts_match")), _tag_matches(pattern))
    return or_(
        func.lower(Problem.title).like(pattern, escape="\\"),
        func.lower(Problem.description).like(pattern, escape="\\"),
        _tag_matches(pattern),
    )


def relevance(query: str, dialect: str) -> ColumnElement | None:
    """A sortable rank (higher = more relevant), or None where the database can't rank."""
    if dialect != "postgresql":
        return None
    return func.ts_rank(literal_column(f"({_DOCUMENT})"), _tsquery(query, "fts_rank"))
