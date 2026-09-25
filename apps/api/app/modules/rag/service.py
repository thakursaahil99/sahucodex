"""RAG: embeds a problem's own public statement (title + description + tags — the same words a solver reads, never
hidden tests) into Qdrant, and answers two questions from that index:

1. "What problems read like this one?" (`similar_problems`) — the problem detail page's "Similar problems" panel.
2. "What problems read like this free-text query?" (`semantic_search`) — a search box, complementing the existing
   keyword `tsvector` search in `app.modules.problems.search` rather than replacing it.

Indexing is called from the admin problems router on publish/update (see `app.modules.admin.problems`) — a
problem's vector is only ever as stale as its last edit, the same staleness contract the keyword search index
already has. A problem that fails to embed (Ollama or Qdrant down) is simply left unindexed; it still works
everywhere else, it just will not surface as a RAG result until the next successful reindex.
"""

from __future__ import annotations

import uuid

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.core.config import Settings
from app.modules.ai.provider import AiUnavailableError, EmbeddingProvider
from app.modules.problems.models import Problem
from app.modules.rag.client import RagUnavailableError

# nomic-embed-text (the default OLLAMA_EMBED_MODEL) produces 768-dim vectors. A different embedding model with a
# different dimension needs a new collection (Qdrant collections are fixed-dimension) — see docs/rag.md.
_VECTOR_SIZE = 768


def _embed_text(title: str, description: str, tags: list[str]) -> str:
    tag_line = f"Tags: {', '.join(tags)}\n\n" if tags else ""
    return f"{title}\n\n{tag_line}{description}"


async def _ensure_collection(qdrant: AsyncQdrantClient, collection: str) -> None:
    if await qdrant.collection_exists(collection):
        return
    await qdrant.create_collection(collection, vectors_config=models.VectorParams(size=_VECTOR_SIZE, distance=models.Distance.COSINE))


async def index_problem(
    qdrant: AsyncQdrantClient, embedder: EmbeddingProvider, settings: Settings, problem: Problem
) -> None:
    """Upserts (or, if unpublished/archived, removes) this problem's vector. Called after a problem is created,
    edited, published, unpublished, or archived — never a background job, so the index never drifts silently out
    of sync with what admins believe they just saved."""
    if not settings.rag_configured:
        return
    if not problem.published or problem.archived_at is not None:
        await remove_problem(qdrant, settings, problem.id)
        return

    text = _embed_text(problem.title, problem.description, [t.name for t in problem.tags])
    try:
        vector = await embedder.embed(model=settings.ollama_embed_model, text=text, timeout_s=30)
        await _ensure_collection(qdrant, settings.qdrant_collection)
        await qdrant.upsert(
            settings.qdrant_collection,
            points=[
                models.PointStruct(
                    id=str(problem.id),
                    vector=vector,
                    payload={"slug": problem.slug, "title": problem.title, "difficulty": problem.difficulty},
                )
            ],
        )
    except (AiUnavailableError, ResponseHandlingException, UnexpectedResponse, OSError):
        # Best-effort: the admin's save/publish action still succeeds (see the router) even if indexing didn't.
        return


async def remove_problem(qdrant: AsyncQdrantClient, settings: Settings, problem_id: uuid.UUID) -> None:
    if not settings.rag_configured:
        return
    try:
        if not await qdrant.collection_exists(settings.qdrant_collection):
            return
        await qdrant.delete(settings.qdrant_collection, points_selector=models.PointIdsList(points=[str(problem_id)]))
    except (ResponseHandlingException, UnexpectedResponse, OSError):
        return


async def _search(
    qdrant: AsyncQdrantClient, embedder: EmbeddingProvider, settings: Settings, text: str, *, exclude: uuid.UUID | None, limit: int
) -> list[uuid.UUID]:
    if not settings.rag_configured:
        raise RagUnavailableError("RAG is not configured on this server (QDRANT_URL is unset)")
    try:
        vector = await embedder.embed(model=settings.ollama_embed_model, text=text, timeout_s=30)
        if not await qdrant.collection_exists(settings.qdrant_collection):
            return []
        query_filter = None
        if exclude is not None:
            query_filter = models.Filter(
                must_not=[models.HasIdCondition(has_id=[str(exclude)])]
            )
        result = await qdrant.query_points(
            settings.qdrant_collection, query=vector, query_filter=query_filter, limit=limit, with_payload=False
        )
    except (AiUnavailableError, ResponseHandlingException, UnexpectedResponse, OSError) as exc:
        raise RagUnavailableError("Could not reach the vector search backend") from exc
    return [uuid.UUID(str(point.id)) for point in result.points]


async def similar_problems(
    qdrant: AsyncQdrantClient, embedder: EmbeddingProvider, settings: Settings, problem: Problem, limit: int | None = None
) -> list[uuid.UUID]:
    """Nearest neighbours of `problem`'s own vector — its own point is excluded from its own results."""
    text = _embed_text(problem.title, problem.description, [t.name for t in problem.tags])
    return await _search(qdrant, embedder, settings, text, exclude=problem.id, limit=limit or settings.rag_top_k)


async def semantic_search(
    qdrant: AsyncQdrantClient, embedder: EmbeddingProvider, settings: Settings, query: str, limit: int | None = None
) -> list[uuid.UUID]:
    return await _search(qdrant, embedder, settings, query, exclude=None, limit=limit or settings.rag_top_k)
