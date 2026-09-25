"""Orchestrates every AI feature: resolve safe problem context, enforce limits, call the provider, record usage.

Every code path here either returns a real model response or raises — there is no canned text standing in for one.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

import anyio
from qdrant_client import AsyncQdrantClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cache import Cache
from app.core.config import Settings
from app.core.errors import AppError, not_found
from app.modules.ai import prompts
from app.modules.ai.models import AiConversation, AiFeature, AiMessage, AiRole, AiUsage
from app.modules.ai.provider import AiProvider, AiUnavailableError, EmbeddingProvider
from app.modules.ai.schemas import CodeRequest, ConversationCreate, ConversationRename, HintRequest
from app.modules.problems import service as problems
from app.modules.problems.models import Problem
from app.modules.problems.schemas import ProblemPublic
from app.modules.rag import service as rag
from app.modules.rag.client import RagUnavailableError
from app.modules.users.models import User

# What every "send a message" call hands back to the router: the conversation, the system prompt for this turn, and
# the message history to send the model (already includes the user's own new message).
StagedReply = tuple[AiConversation, str, list[tuple[str, str]]]


def require_configured(settings: Settings) -> None:
    if not settings.ai_configured:
        raise AppError(
            503,
            "AI_UNAVAILABLE",
            "SahuCodeX AI is not configured on this server yet. Set OLLAMA_MODEL to enable it.",
        )


async def _resolve_problem(db: AsyncSession, cache: Cache, slug: str | None) -> ProblemPublic | None:
    if slug is None:
        return None
    problem = await problems.get_public_problem(db, cache, slug)
    if problem is None:
        raise not_found("PROBLEM_NOT_FOUND", "Problem not found")
    return problem


async def _related_problems(
    db: AsyncSession, qdrant: AsyncQdrantClient, embedder: EmbeddingProvider, settings: Settings, message: str
) -> list[tuple[str, str, str]]:
    """Best-effort RAG context for an open-ended chat message with no problem already attached (see
    `prompts.chat_system_prompt`). Never raises: an unconfigured or unreachable RAG backend just means chat
    proceeds with no extra context, exactly as it did before this feature existed."""
    if not settings.rag_configured:
        return []
    try:
        ids = await rag.semantic_search(qdrant, embedder, settings, message, limit=3)
    except RagUnavailableError:
        return []
    if not ids:
        return []
    rows = (
        await db.execute(
            select(Problem.id, Problem.slug, Problem.title, Problem.difficulty).where(
                Problem.id.in_(ids), Problem.published.is_(True), Problem.archived_at.is_(None)
            )
        )
    ).all()
    by_id = {row.id: row for row in rows}
    # Preserve Qdrant's relevance order, not the DB's — a plain WHERE ... IN does not guarantee it.
    ordered = [by_id[i] for i in ids if i in by_id]
    return [(row.slug, row.title, row.difficulty) for row in ordered]


def _check_length(settings: Settings, text: str, field: str) -> None:
    if len(text) > settings.ai_max_prompt_chars:
        raise AppError(422, "AI_INPUT_TOO_LARGE", f"{field} is limited to {settings.ai_max_prompt_chars} characters")


async def _record_usage(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    feature: AiFeature,
    model: str,
    prompt_chars: int,
    response_chars: int,
    duration_ms: int,
    failed: bool,
    conversation_id: uuid.UUID | None = None,
) -> None:
    db.add(
        AiUsage(
            user_id=user_id,
            feature=feature.value,
            model=model,
            conversation_id=conversation_id,
            prompt_chars=prompt_chars,
            response_chars=response_chars,
            duration_ms=duration_ms,
            failed=failed,
        )
    )
    await db.commit()


async def _generate(
    db: AsyncSession,
    provider: AiProvider,
    settings: Settings,
    user: User,
    feature: AiFeature,
    system: str,
    prompt: str,
) -> str:
    _check_length(settings, prompt, "Input")
    started = time.monotonic()
    try:
        result = await provider.generate(
            system=system,
            prompt=prompt,
            max_tokens=settings.ai_max_response_tokens,
            timeout_s=settings.ai_request_timeout,
        )
    except AiUnavailableError as exc:
        await _record_usage(
            db,
            user_id=user.id,
            feature=feature,
            model=provider.model,
            prompt_chars=len(prompt),
            response_chars=0,
            duration_ms=int((time.monotonic() - started) * 1000),
            failed=True,
        )
        raise AppError(503, "AI_UNAVAILABLE", "SahuCodeX AI could not answer right now. Please try again.") from exc
    await _record_usage(
        db,
        user_id=user.id,
        feature=feature,
        model=provider.model,
        prompt_chars=len(prompt),
        response_chars=len(result.text),
        duration_ms=result.duration_ms,
        failed=False,
    )
    return result.text


async def get_hint(
    db: AsyncSession, cache: Cache, provider: AiProvider, settings: Settings, user: User, data: HintRequest
) -> str:
    problem = await _resolve_problem(db, cache, data.problem_slug)
    assert problem is not None  # HintRequest.problem_slug is required
    system, prompt = prompts.hint_prompt(problem, data.language, data.code, data.previous_hints)
    return await _generate(db, provider, settings, user, AiFeature.HINT, system, prompt)


async def get_explanation(
    db: AsyncSession, cache: Cache, provider: AiProvider, settings: Settings, user: User, data: CodeRequest
) -> str:
    problem = await _resolve_problem(db, cache, data.problem_slug)
    system, prompt = prompts.explain_prompt(problem, data.language, data.code)
    return await _generate(db, provider, settings, user, AiFeature.EXPLAIN, system, prompt)


async def get_review(
    db: AsyncSession, cache: Cache, provider: AiProvider, settings: Settings, user: User, data: CodeRequest
) -> str:
    problem = await _resolve_problem(db, cache, data.problem_slug)
    system, prompt = prompts.review_prompt(problem, data.language, data.code)
    return await _generate(db, provider, settings, user, AiFeature.REVIEW, system, prompt)


# --- conversations -------------------------------------------------------------------------------------------------


def _title_from(message: str) -> str:
    first_line = message.strip().splitlines()[0] if message.strip() else "New conversation"
    return first_line[:117] + "…" if len(first_line) > 120 else first_line


async def create_conversation(
    db: AsyncSession,
    cache: Cache,
    settings: Settings,
    user: User,
    data: ConversationCreate,
    qdrant: AsyncQdrantClient,
    embedder: EmbeddingProvider,
) -> StagedReply:
    """Creates the conversation with its first (user) message, and returns exactly what `stream_reply` needs — the
    same shape `prepare_reply` returns for every later message, so the router treats "first message" and "next
    message" identically."""
    problem = await _resolve_problem(db, cache, data.problem_slug)  # 404s early if the slug is wrong
    _check_length(settings, data.message, "Message")

    count = await db.scalar(select(func.count()).select_from(AiConversation).where(AiConversation.user_id == user.id))
    if (count or 0) >= settings.ai_max_conversations:
        raise AppError(
            409,
            "TOO_MANY_CONVERSATIONS",
            f"You can have at most {settings.ai_max_conversations} conversations. Delete one to start another.",
        )

    conversation = AiConversation(
        user_id=user.id, title=_title_from(data.message), problem_slug=problem.slug if problem else None
    )
    conversation.messages = [AiMessage(role=AiRole.USER.value, content=data.message)]
    db.add(conversation)
    await db.commit()

    related = [] if problem else await _related_problems(db, qdrant, embedder, settings, data.message)
    system = prompts.chat_system_prompt(problem, related)
    history = [(m.role, m.content) for m in conversation.messages]
    return conversation, system, history


async def get_owned_conversation(db: AsyncSession, user: User, conversation_id: uuid.UUID) -> AiConversation:
    """Owner-only. A stranger's id gets the same 404 a missing one would, so ids cannot be probed."""
    conversation = await db.get(AiConversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise not_found("CONVERSATION_NOT_FOUND", "Conversation not found")
    return conversation


async def list_conversations(db: AsyncSession, user: User) -> list[AiConversation]:
    rows = await db.scalars(
        select(AiConversation).where(AiConversation.user_id == user.id).order_by(AiConversation.updated_at.desc())
    )
    return list(rows.all())


async def rename_conversation(
    db: AsyncSession, user: User, conversation_id: uuid.UUID, data: ConversationRename
) -> AiConversation:
    conversation = await get_owned_conversation(db, user, conversation_id)
    conversation.title = data.title.strip() or conversation.title
    await db.commit()
    return conversation


async def delete_conversation(db: AsyncSession, user: User, conversation_id: uuid.UUID) -> None:
    conversation = await get_owned_conversation(db, user, conversation_id)
    await db.delete(conversation)
    await db.commit()


async def prepare_reply(
    db: AsyncSession,
    cache: Cache,
    settings: Settings,
    user: User,
    conversation_id: uuid.UUID,
    content: str,
    qdrant: AsyncQdrantClient,
    embedder: EmbeddingProvider,
) -> StagedReply:
    """Stages the user's message and returns everything `stream_reply` needs. Split out so the router can send the
    user's own message back immediately, before the (possibly slow) model call starts."""
    conversation = await get_owned_conversation(db, user, conversation_id)
    _check_length(settings, content, "Message")
    if len(conversation.messages) >= settings.ai_max_messages_per_conversation:
        raise AppError(409, "CONVERSATION_FULL", "This conversation has reached its message limit. Start a new one.")

    problem = await _resolve_problem(db, cache, conversation.problem_slug)
    related = [] if problem else await _related_problems(db, qdrant, embedder, settings, content)
    system = prompts.chat_system_prompt(problem, related)
    history: list[tuple[str, str]] = [(m.role, m.content) for m in conversation.messages]
    history.append((AiRole.USER.value, content))

    conversation.messages.append(AiMessage(role=AiRole.USER.value, content=content))
    await db.commit()
    return conversation, system, history


async def stream_reply(
    db_factory: async_sessionmaker[AsyncSession],
    provider: AiProvider,
    settings: Settings,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    system: str,
    history: list[tuple[str, str]],
) -> AsyncIterator[str]:
    """Streams the model's reply token by token, then persists whatever was generated and a usage row in a fresh
    session (the request's own session is already closed by the time streaming finishes).

    Persisting happens in `finally`, shielded from cancellation, so a user who presses Stop or closes the tab still
    gets their partial reply kept and the request metered — an abandoned request costs the model just as much."""
    started = time.monotonic()
    chunks: list[str] = []
    failed = False
    try:
        async for token in provider.stream_chat(
            system=system,
            messages=history,
            max_tokens=settings.ai_max_response_tokens,
            timeout_s=settings.ai_request_timeout,
        ):
            chunks.append(token)
            yield token
    except AiUnavailableError:
        failed = True
    finally:
        with anyio.CancelScope(shield=True):
            await _persist_reply(
                db_factory,
                provider.model,
                user_id,
                conversation_id,
                history,
                "".join(chunks),
                failed=failed,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
    if failed:
        # Whatever was generated before the failure is kept above; the caller still has to tell the client.
        raise AiUnavailableError("the model stopped responding")


async def _persist_reply(
    db_factory: async_sessionmaker[AsyncSession],
    model: str,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    history: list[tuple[str, str]],
    text: str,
    *,
    failed: bool,
    duration_ms: int,
) -> None:
    async with db_factory() as db:
        if text:
            conversation = await db.get(AiConversation, conversation_id)
            if conversation is not None:
                conversation.messages.append(AiMessage(role=AiRole.ASSISTANT.value, content=text))
        await _record_usage(
            db,
            user_id=user_id,
            feature=AiFeature.CHAT,
            model=model,
            prompt_chars=sum(len(content) for _, content in history),
            response_chars=len(text),
            duration_ms=duration_ms,
            failed=failed,
            conversation_id=conversation_id,
        )
