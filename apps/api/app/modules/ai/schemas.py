"""Request and response models for SahuCodeX AI.

Nothing here can carry a hidden test — the only problem data these requests can *reference* is a slug the server
resolves through the same public lookup the problem API uses (see prompts.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.ai.models import AiFeature, AiRole
from app.modules.submissions.schemas import LANGUAGE_PATTERN, SLUG_PATTERN

# A hard ceiling for parsing only; the configured limit (AI_MAX_PROMPT_CHARS) is checked in the service, so an
# operator can tune it without a code change.
MAX_CODE_CHARS = 20_000
MAX_MESSAGE_CHARS = 8_000
MAX_HINTS_LISTED = 10


class HintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_slug: str = Field(max_length=80, pattern=SLUG_PATTERN)
    language: str = Field(pattern=LANGUAGE_PATTERN)
    code: str = Field(min_length=1, max_length=MAX_CODE_CHARS)
    previous_hints: list[str] = Field(default_factory=list, max_length=MAX_HINTS_LISTED)


class CodeRequest(BaseModel):
    """Explain and Review take the same shape: optional problem context, language, code."""

    model_config = ConfigDict(extra="forbid")

    problem_slug: str | None = Field(default=None, max_length=80, pattern=SLUG_PATTERN)
    language: str = Field(pattern=LANGUAGE_PATTERN)
    code: str = Field(min_length=1, max_length=MAX_CODE_CHARS)


class AiStatus(BaseModel):
    """Whether the server has a model chosen. Deliberately no network probe: a down server shows up honestly as a 503
    on the real call, and this endpoint stays cheap enough for the UI to fetch on every page."""

    configured: bool
    model: str | None


class GenerationOut(BaseModel):
    feature: AiFeature
    content: str
    model: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: AiRole
    content: str
    created_at: datetime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    problem_slug: str | None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut]


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_slug: str | None = Field(default=None, max_length=80, pattern=SLUG_PATTERN)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ConversationRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
