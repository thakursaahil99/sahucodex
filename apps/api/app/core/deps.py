"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import Cache
from app.core.config import Settings
from app.core.db import get_db
from app.core.email import EmailSender
from app.modules.ai.provider import AiProvider, OllamaProvider


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def get_cache(request: Request) -> Cache:
    return request.app.state.cache


def get_email_sender(request: Request) -> EmailSender:
    return request.app.state.email_sender


def get_qdrant(request: Request) -> AsyncQdrantClient:
    return request.app.state.qdrant


def get_ai_provider(request: Request) -> AiProvider:
    return request.app.state.ai_provider


def get_embedding_provider(request: Request) -> OllamaProvider:
    """Embeddings always go straight to Ollama, independent of AI_PROVIDER (which only picks the *chat* backend —
    OpenRouter has no embeddings wiring here, see `app.modules.ai.provider`). A dedicated client, not
    `app.state.ai_provider`, so RAG keeps working even when AI_PROVIDER=openrouter."""
    return request.app.state.embedding_provider


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
RedisDep = Annotated[Redis, Depends(get_redis)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
CacheDep = Annotated[Cache, Depends(get_cache)]
EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]
QdrantDep = Annotated[AsyncQdrantClient, Depends(get_qdrant)]
AiProviderDep = Annotated[AiProvider, Depends(get_ai_provider)]
EmbeddingProviderDep = Annotated[OllamaProvider, Depends(get_embedding_provider)]
