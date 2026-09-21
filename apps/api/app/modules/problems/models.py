from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JsonType, TimestampMixin, utcnow


class Difficulty(enum.StrEnum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class CaseKind(enum.StrEnum):
    """PUBLIC cases are visible to users (and used by Run); HIDDEN cases never leave the server."""

    PUBLIC = "PUBLIC"
    HIDDEN = "HIDDEN"


class ProgressStatus(enum.StrEnum):
    ATTEMPTED = "ATTEMPTED"
    SOLVED = "SOLVED"


class ProgrammingLanguage(Base):
    """Reference table, seeded by the migration. Adding a language later is a data change plus a runner."""

    __tablename__ = "programming_languages"

    key: Mapped[str] = mapped_column(String(20), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(60))
    editor_language: Mapped[str] = mapped_column(String(30))  # Monaco language id
    file_extension: Mapped[str] = mapped_column(String(10))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)


class ProblemTag(Base):
    __tablename__ = "problem_tags"

    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True)


class Problem(Base, TimestampMixin):
    __tablename__ = "problems"
    __table_args__ = (
        Index("ix_problems_listing", "published", "archived_at", "difficulty"),
        CheckConstraint("time_limit_ms BETWEEN 100 AND 10000", name="time_limit_range"),
        CheckConstraint("memory_limit_mb BETWEEN 16 AND 1024", name="memory_limit_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)  # Markdown
    difficulty: Mapped[str] = mapped_column(String(10))
    constraints: Mapped[str] = mapped_column(Text)
    input_format: Mapped[str] = mapped_column(Text)
    output_format: Mapped[str] = mapped_column(Text)
    time_limit_ms: Mapped[int] = mapped_column(Integer, default=2000, server_default=text("2000"))
    memory_limit_mb: Mapped[int] = mapped_column(Integer, default=256, server_default=text("256"))
    checker: Mapped[str] = mapped_column(String(20), default="lines", server_default="lines")
    editorial: Mapped[str | None] = mapped_column(Text)
    hints: Mapped[list[str]] = mapped_column(JsonType, default=list)
    function_signature: Mapped[str | None] = mapped_column(String(300))
    expected_time_complexity: Mapped[str | None] = mapped_column(String(60))
    expected_space_complexity: Mapped[str | None] = mapped_column(String(60))

    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    published_at: Mapped[datetime | None]
    archived_at: Mapped[datetime | None]  # soft delete: archived problems vanish from the public API

    # Denormalised counters, maintained by SahuJudge (phase 3). They make acceptance-rate filtering and
    # sorting a cheap indexed read instead of an aggregate over every submission.
    total_submissions: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    accepted_submissions: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))

    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    tags: Mapped[list[Tag]] = relationship(secondary="problem_tags", lazy="selectin", order_by="Tag.name")
    examples: Mapped[list[ProblemExample]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProblemExample.position",
    )
    test_cases: Mapped[list[ProblemTestCase]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProblemTestCase.position",
    )
    starter_codes: Mapped[list[ProblemStarterCode]] = relationship(
        back_populates="problem", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def acceptance_rate(self) -> float | None:
        if not self.total_submissions:
            return None
        return round(self.accepted_submissions * 100 / self.total_submissions, 1)


class ProblemTestCase(Base):
    __tablename__ = "problem_test_cases"
    __table_args__ = (Index("ix_problem_test_cases_problem_kind", "problem_id", "kind", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))
    position: Mapped[int] = mapped_column(Integer)
    input_data: Mapped[str] = mapped_column(Text)
    expected_output: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())

    problem: Mapped[Problem] = relationship(back_populates="test_cases")


class ProblemExample(Base):
    """A PUBLIC test case promoted into the statement, with an optional explanation.

    Examples reference their test case instead of copying its input/output, so the data lives once."""

    __tablename__ = "problem_examples"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    test_case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("problem_test_cases.id", ondelete="CASCADE"), unique=True
    )
    position: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str | None] = mapped_column(Text)

    problem: Mapped[Problem] = relationship(back_populates="examples")
    test_case: Mapped[ProblemTestCase] = relationship(lazy="selectin")


class ProblemStarterCode(Base):
    __tablename__ = "problem_starter_code"

    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True)
    language_key: Mapped[str] = mapped_column(
        ForeignKey("programming_languages.key", ondelete="CASCADE"), primary_key=True
    )
    code: Mapped[str] = mapped_column(Text)

    problem: Mapped[Problem] = relationship(back_populates="starter_codes")


class UserProblemProgress(Base):
    """Per-user, per-problem status. Written by SahuJudge (phase 3); read here for filters and editorial access."""

    __tablename__ = "user_problem_progress"
    __table_args__ = (Index("ix_user_problem_progress_problem", "problem_id", "status"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(10))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    first_solved_at: Mapped[datetime | None]
    last_attempt_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=func.now())
