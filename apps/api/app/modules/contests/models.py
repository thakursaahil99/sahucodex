"""Contests: a timed set of problems, who has registered, and (via `Submission.contest_id`) what they submitted.

Standings are never stored — they are computed on demand from `submissions` (see `service.compute_standings`). This
keeps there being exactly one place a verdict is decided (SahuJudge) and exactly one place a score is derived from it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UTCDateTime


class Contest(Base, TimestampMixin):
    __tablename__ = "contests"
    __table_args__ = (Index("ix_contests_published_start", "published", "start_time"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    start_time: Mapped[datetime] = mapped_column(UTCDateTime())
    end_time: Mapped[datetime] = mapped_column(UTCDateTime())
    # Minutes added to a solved problem's score time for each earlier non-accepted attempt on it (ICPC-style).
    penalty_minutes: Mapped[int] = mapped_column(Integer, default=20, server_default=text("20"))
    published: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    problems: Mapped[list[ContestProblem]] = relationship(
        back_populates="contest", cascade="all, delete-orphan", lazy="selectin", order_by="ContestProblem.label"
    )


class ContestProblem(Base):
    __tablename__ = "contest_problems"
    __table_args__ = (
        UniqueConstraint("contest_id", "label", name="uq_contest_problems_contest_label"),
        UniqueConstraint("contest_id", "problem_id", name="uq_contest_problems_contest_problem"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    contest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contests.id", ondelete="CASCADE"))
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="RESTRICT"))
    label: Mapped[str] = mapped_column(String(4))  # "A", "B", "C", ... — display order and identity within a contest
    points: Mapped[int] = mapped_column(Integer, default=100, server_default=text("100"))

    contest: Mapped[Contest] = relationship(back_populates="problems")


class ContestParticipant(Base):
    """Registering is what makes a submission count toward standings — see service.compute_standings."""

    __tablename__ = "contest_participants"
    __table_args__ = (Index("ix_contest_participants_contest", "contest_id"),)

    contest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contests.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    registered_at: Mapped[datetime] = mapped_column(UTCDateTime())
