"""RAG API: semantic problem search and "similar problems". Both 503 cleanly when RAG isn't configured (see
`Settings.rag_configured`) — never an empty list standing in for "no results", which would be indistinguishable
from a real empty result.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.deps import DbSession, EmbeddingProviderDep, QdrantDep, SettingsDep
from app.core.errors import AppError, not_found
from app.modules.problems import service as problems
from app.modules.problems.models import Problem
from app.modules.problems.schemas import ProblemListItem, TagOut
from app.modules.rag import service as svc
from app.modules.rag.client import RagUnavailableError

router = APIRouter(tags=["rag"])


def _require_configured(settings: SettingsDep) -> None:
    if not settings.rag_configured:
        raise AppError(503, "RAG_UNAVAILABLE", "Semantic search is not configured on this server yet.")


async def _resolve(db: DbSession, ids: list[uuid.UUID]) -> list[ProblemListItem]:
    """Looks up Qdrant's id hits against the DB, drops anything no longer public (deleted/unpublished since it was
    indexed), and keeps Qdrant's own relevance order rather than the DB's."""
    if not ids:
        return []
    rows = list(
        (
            await db.scalars(
                select(Problem).where(Problem.id.in_(ids), Problem.published.is_(True), Problem.archived_at.is_(None))
            )
        ).unique()
    )
    by_id = {row.id: row for row in rows}
    ordered = [by_id[i] for i in ids if i in by_id]
    return [
        ProblemListItem(
            slug=p.slug,
            title=p.title,
            difficulty=p.difficulty,
            tags=[TagOut(name=t.name, slug=t.slug) for t in p.tags],
            acceptance_rate=p.acceptance_rate,
            total_submissions=p.total_submissions,
            status=None,
        )
        for p in ordered
    ]


@router.get("/problems/{slug}/similar", response_model=list[ProblemListItem])
async def get_similar_problems(
    slug: str, db: DbSession, qdrant: QdrantDep, embedder: EmbeddingProviderDep, settings: SettingsDep
) -> list[ProblemListItem]:
    _require_configured(settings)
    problem = await problems.find_visible_problem(db, slug)
    if problem is None:
        raise not_found("PROBLEM_NOT_FOUND", "Problem not found")
    try:
        ids = await svc.similar_problems(qdrant, embedder, settings, problem)
    except RagUnavailableError as exc:
        raise AppError(503, "RAG_UNAVAILABLE", "Semantic search could not answer right now. Please try again.") from exc
    return await _resolve(db, ids)


@router.get("/search/semantic", response_model=list[ProblemListItem])
async def semantic_search(
    db: DbSession,
    qdrant: QdrantDep,
    embedder: EmbeddingProviderDep,
    settings: SettingsDep,
    q: str = Query(min_length=1, max_length=300),
) -> list[ProblemListItem]:
    _require_configured(settings)
    try:
        ids = await svc.semantic_search(qdrant, embedder, settings, q)
    except RagUnavailableError as exc:
        raise AppError(503, "RAG_UNAVAILABLE", "Semantic search could not answer right now. Please try again.") from exc
    return await _resolve(db, ids)
