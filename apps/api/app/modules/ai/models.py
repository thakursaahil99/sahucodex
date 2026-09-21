"""SahuCodeX AI: chat conversations and per-request usage records.

Hint/Explain/Review are one-off generations — they are metered (`AiUsage`) but not stored as a conversation. Only the
free-form Assistant chat (`/ai`) persists a transcript.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UTCDateTime, utcnow


class AiRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class AiFeature(enum.StrEnum):
    HINT = "hint"
    EXPLAIN = "explain"
    REVIEW = "review"
    CHAT = "chat"


class AiConversation(Base, TimestampMixin):
    __tablename__ = "ai_conversations"
    __table_args__ = (Index("ix_ai_conversations_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    # Display-only label of what problem (if any) the chat started from — deliberately NOT a foreign key, so an
    # archived or renamed problem never breaks a conversation, and the AI is never handed a problem id to look up.
    problem_slug: Mapped[str | None] = mapped_column(String(80))

    messages: Mapped[list[AiMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="AiMessage.created_at",
    )


class AiMessage(Base):
    __tablename__ = "ai_messages"
    __table_args__ = (Index("ix_ai_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, server_default=func.now())

    conversation: Mapped[AiConversation] = relationship(back_populates="messages")


class AiUsage(Base):
    """One row per AI request, win or lose — a failed/timed-out call is recorded too, with `response_chars=0`, so
    abuse counting and cost visibility do not depend on the model actually answering."""

    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    feature: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(80))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_conversations.id", ondelete="SET NULL"))
    prompt_chars: Mapped[int] = mapped_column(Integer)
    response_chars: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    failed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, server_default=func.now())
