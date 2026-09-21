"""SahuCodeX AI: one-off generations (hint/explain/review) and the streaming Assistant chat.

Every route enforces `require_configured` and the shared `ai` rate limit before doing anything expensive. Streaming
uses a plain `text/event-stream` response over normal HTTP (unlike the submissions WebSocket, a browser can send the
`Authorization` header on this request directly, so no ticket dance is needed here).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette import status

from app.core.config import Settings
from app.core.deps import CacheDep, DbSession, SettingsDep
from app.core.rate_limit import get_rate_limiter
from app.modules.ai import service
from app.modules.ai.models import AiConversation
from app.modules.ai.provider import AiProvider, AiUnavailableError
from app.modules.ai.schemas import (
    AiStatus,
    CodeRequest,
    ConversationCreate,
    ConversationDetail,
    ConversationRename,
    ConversationSummary,
    GenerationOut,
    HintRequest,
    MessageCreate,
)
from app.modules.auth.deps import CurrentUser

router = APIRouter(prefix="/ai", tags=["ai"])


def get_ai_provider(request: Request) -> AiProvider:
    return request.app.state.ai_provider


async def _enforce(request: Request, settings: SettingsDep, user: CurrentUser) -> None:
    service.require_configured(settings)
    await get_rate_limiter(request).enforce("ai", str(user.id), settings.rate_limit_ai)


@router.get("/status", response_model=AiStatus)
async def status_(user: CurrentUser, settings: SettingsDep) -> AiStatus:
    return AiStatus(configured=settings.ai_configured, model=settings.ollama_model or None)


@router.post("/hint", response_model=GenerationOut)
async def hint(
    data: HintRequest, request: Request, user: CurrentUser, db: DbSession, cache: CacheDep, settings: SettingsDep
) -> GenerationOut:
    await _enforce(request, settings, user)
    provider = get_ai_provider(request)
    text = await service.get_hint(db, cache, provider, settings, user, data)
    return GenerationOut(feature="hint", content=text, model=provider.model)


@router.post("/explain", response_model=GenerationOut)
async def explain(
    data: CodeRequest, request: Request, user: CurrentUser, db: DbSession, cache: CacheDep, settings: SettingsDep
) -> GenerationOut:
    await _enforce(request, settings, user)
    provider = get_ai_provider(request)
    text = await service.get_explanation(db, cache, provider, settings, user, data)
    return GenerationOut(feature="explain", content=text, model=provider.model)


@router.post("/review", response_model=GenerationOut)
async def review(
    data: CodeRequest, request: Request, user: CurrentUser, db: DbSession, cache: CacheDep, settings: SettingsDep
) -> GenerationOut:
    await _enforce(request, settings, user)
    provider = get_ai_provider(request)
    text = await service.get_review(db, cache, provider, settings, user, data)
    return GenerationOut(feature="review", content=text, model=provider.model)


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(user: CurrentUser, db: DbSession) -> list[AiConversation]:
    return await service.list_conversations(db, user)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: DbSession) -> AiConversation:
    return await service.get_owned_conversation(db, user, conversation_id)


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
async def rename_conversation(
    conversation_id: uuid.UUID, data: ConversationRename, user: CurrentUser, db: DbSession
) -> AiConversation:
    return await service.rename_conversation(db, user, conversation_id, data)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    await service.delete_conversation(db, user, conversation_id)


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n".encode()


async def _sse_stream(
    request: Request,
    settings: Settings,
    provider: AiProvider,
    user_id: uuid.UUID,
    conversation: AiConversation,
    system: str,
    history: list[tuple[str, str]],
) -> AsyncIterator[bytes]:
    yield _sse("start", {"conversation_id": str(conversation.id)})
    try:
        async for token in service.stream_reply(
            request.app.state.sessionmaker, provider, settings, user_id, conversation.id, system, history
        ):
            yield _sse("token", {"content": token})
    except AiUnavailableError:
        # The 200 and headers are already sent, so a failure can only be reported in-band.
        yield _sse("error", {"code": "AI_UNAVAILABLE", "message": "SahuCodeX AI stopped responding. Please retry."})
        return
    yield _sse("done", {})


def _stream(
    request: Request, settings: Settings, provider: AiProvider, user_id: uuid.UUID, staged: service.StagedReply
) -> StreamingResponse:
    conversation, system, history = staged
    return StreamingResponse(
        _sse_stream(request, settings, provider, user_id, conversation, system, history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/conversations", status_code=status.HTTP_200_OK)
async def create_conversation(
    data: ConversationCreate, request: Request, user: CurrentUser, db: DbSession, cache: CacheDep, settings: SettingsDep
) -> StreamingResponse:
    await _enforce(request, settings, user)
    provider = get_ai_provider(request)
    staged = await service.create_conversation(db, cache, settings, user, data)
    return _stream(request, settings, provider, user.id, staged)


@router.post("/conversations/{conversation_id}/messages", status_code=status.HTTP_200_OK)
async def send_message(
    conversation_id: uuid.UUID,
    data: MessageCreate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    cache: CacheDep,
    settings: SettingsDep,
) -> StreamingResponse:
    await _enforce(request, settings, user)
    provider = get_ai_provider(request)
    staged = await service.prepare_reply(db, cache, settings, user, conversation_id, data.content)
    return _stream(request, settings, provider, user.id, staged)
