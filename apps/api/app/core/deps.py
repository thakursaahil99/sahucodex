"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import Cache
from app.core.config import Settings
from app.core.db import get_db
from app.core.email import EmailSender


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def get_cache(request: Request) -> Cache:
    return request.app.state.cache


def get_email_sender(request: Request) -> EmailSender:
    return request.app.state.email_sender


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
RedisDep = Annotated[Redis, Depends(get_redis)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
CacheDep = Annotated[Cache, Depends(get_cache)]
EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]
