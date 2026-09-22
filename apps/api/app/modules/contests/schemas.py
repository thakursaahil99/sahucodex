"""Request/response models for contests.

`ContestProblemOut` wraps the exact same `ProblemPublic` the plain problem API returns — hidden tests and the
editorial can't leak here any more than they can there. Before a contest starts, no problem content is ever sent at
all (not even behind a flag): `list_problems_out`/`get_contest_problem` refuse outright.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.problems.schemas import ProblemPublic
from app.modules.submissions.schemas import LANGUAGE_PATTERN, MAX_SOURCE_CHARS

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
LABEL_PATTERN = r"^[A-Z][A-Z0-9]?$"  # "A".."Z", "A1".."Z9" — short, sortable, admin-chosen

ContestPhase = Literal["upcoming", "running", "ended"]


class ContestProblemRef(BaseModel):
    """Just enough to render the problem list/standings header before (or without) fetching each statement."""

    label: str
    points: int
    title: str | None  # withheld (None) for a contest that has not started yet


class ContestListItem(BaseModel):
    slug: str
    title: str
    start_time: datetime
    end_time: datetime
    phase: ContestPhase
    problem_count: int


class ContestDetail(ContestListItem):
    description: str
    penalty_minutes: int
    problems: list[ContestProblemRef]
    registered: bool  # false for an anonymous caller


class ContestProblemOut(BaseModel):
    label: str
    points: int
    problem: ProblemPublic


class ContestSubmitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(pattern=LANGUAGE_PATTERN)
    source_code: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)


class ContestRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(pattern=LANGUAGE_PATTERN)
    source_code: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)
    mode: Literal["samples", "custom"] = "samples"
    input: str | None = Field(default=None, max_length=MAX_SOURCE_CHARS)


class StandingsCell(BaseModel):
    solved: bool
    attempts: int  # non-accepted attempts before solving (or total attempts, if never solved)
    penalty_minutes: int  # 0 unless solved


class StandingsRow(BaseModel):
    rank: int
    username: str
    total_points: int
    total_penalty_minutes: int
    cells: dict[str, StandingsCell]  # keyed by problem label


class StandingsOut(BaseModel):
    generated_at: datetime
    problems: list[ContestProblemRef]
    rows: list[StandingsRow]


# --- admin --------------------------------------------------------------------------------------------------------


class ContestAdminProblemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_slug: str = Field(max_length=80, pattern=SLUG_PATTERN)
    label: str = Field(pattern=LABEL_PATTERN)
    points: int = Field(ge=0, le=100_000)


class ContestAdminInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(max_length=80, pattern=SLUG_PATTERN)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20_000)
    start_time: datetime
    end_time: datetime
    penalty_minutes: int = Field(default=20, ge=0, le=1_000)
    problems: list[ContestAdminProblemInput] = Field(default_factory=list, max_length=26)

    @model_validator(mode="after")
    def _check(self) -> ContestAdminInput:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        labels = [p.label for p in self.problems]
        if len(labels) != len(set(labels)):
            raise ValueError("problem labels must be unique within a contest")
        slugs = [p.problem_slug for p in self.problems]
        if len(slugs) != len(set(slugs)):
            raise ValueError("a problem may only appear once in a contest")
        return self


class ContestAdminProblemOut(BaseModel):
    label: str
    points: int
    problem_slug: str
    problem_title: str


class ContestAdminOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str
    start_time: datetime
    end_time: datetime
    penalty_minutes: int
    published: bool
    problems: list[ContestAdminProblemOut]
    created_at: datetime
    updated_at: datetime
