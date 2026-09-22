"""SahuJudge persistence: submissions, their final result, and per-test outcomes.

What is (and is not) stored is a security decision:

* `submissions` holds the user's own source and the *aggregate* outcome (verdict, runtime, memory, passed/total).
* `submission_results` holds the compiler output (the user's own diagnostics) and a short judge message.
* `submission_test_results` holds a verdict/runtime/memory per executed test but **never** test input, expected output
  or the program's output for hidden tests. The API never exposes per-test rows for hidden tests either.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, UTCDateTime, utcnow


class SubmissionStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"  # the judge produced a verdict (which may itself be WRONG_ANSWER, SYSTEM_ERROR, ...)
    FAILED = "FAILED"  # the judge could not finish; the verdict is SYSTEM_ERROR and the attempt is not counted


class Verdict(enum.StrEnum):
    ACCEPTED = "ACCEPTED"
    WRONG_ANSWER = "WRONG_ANSWER"
    TIME_LIMIT_EXCEEDED = "TIME_LIMIT_EXCEEDED"
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        Index("ix_submissions_user_created", "user_id", "created_at"),
        Index("ix_submissions_user_problem", "user_id", "problem_id", "created_at"),
        Index("ix_submissions_status_created", "status", "created_at"),
        Index("ix_submissions_contest_user_problem", "contest_id", "user_id", "problem_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"))
    language_key: Mapped[str] = mapped_column(ForeignKey("programming_languages.key", ondelete="RESTRICT"))
    source_code: Mapped[str] = mapped_column(Text)
    # Set only when submitted through a contest's own submit path (never client-supplied on the normal one). Scoring
    # (contests/service.py) reads this plus `created_at` against the contest's [start_time, end_time] window — never
    # a client-supplied flag — to decide what counts.
    contest_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contests.id", ondelete="SET NULL"))

    status: Mapped[str] = mapped_column(String(12), default=SubmissionStatus.QUEUED, server_default="QUEUED")
    verdict: Mapped[str | None] = mapped_column(String(24))
    runtime_ms: Mapped[int | None] = mapped_column(Integer)
    memory_kb: Mapped[int | None] = mapped_column(Integer)
    passed_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    total_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]

    result: Mapped[SubmissionResult | None] = relationship(
        back_populates="submission", cascade="all, delete-orphan", lazy="raise", uselist=False
    )
    test_results: Mapped[list[SubmissionTestResult]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        lazy="raise",
        order_by="SubmissionTestResult.position",
    )


class SubmissionResult(Base):
    """1:1 with a judged submission: the parts of the outcome that are not needed to list submissions."""

    __tablename__ = "submission_results"

    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), primary_key=True)
    compile_output: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(String(300))  # judge-authored, never derived from hidden data
    checker: Mapped[str] = mapped_column(String(20))
    judge_version: Mapped[str] = mapped_column(String(20))
    time_limit_ms: Mapped[int] = mapped_column(Integer)  # the effective limit applied (after language multiplier)
    memory_limit_mb: Mapped[int] = mapped_column(Integer)

    submission: Mapped[Submission] = relationship(back_populates="result")


class SubmissionTestResult(Base):
    __tablename__ = "submission_test_results"
    __table_args__ = (Index("ix_submission_test_results_submission", "submission_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    # SET NULL: an admin may later replace a test; the historical verdict must survive that.
    test_case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("problem_test_cases.id", ondelete="SET NULL"))
    position: Mapped[int] = mapped_column(Integer)  # 1-based execution order
    is_public: Mapped[bool]
    verdict: Mapped[str] = mapped_column(String(24))
    runtime_ms: Mapped[int | None] = mapped_column(Integer)
    memory_kb: Mapped[int | None] = mapped_column(Integer)

    submission: Mapped[Submission] = relationship(back_populates="test_results")
