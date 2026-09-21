from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.problems.models import CaseKind, Difficulty

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
MAX_CASE_CHARS = 1_000_000  # per test-case input or expected output
MAX_TEST_CASES = 200
MAX_TAGS_PER_PROBLEM = 10
MAX_HINTS = 10
_SLUG_RE = re.compile(SLUG_PATTERN)


# --- Public (what any visitor may see) ----------------------------------------------------------


# How a submission's output is compared with the expected output (see sahujudge/checkers.py).
CheckerName = Literal["exact", "whitespace", "lines"]


class TagOut(BaseModel):
    name: str
    slug: str


class TagWithCount(TagOut):
    problem_count: int


class LanguageOut(BaseModel):
    key: str
    display_name: str
    editor_language: str
    file_extension: str


class ProblemListItem(BaseModel):
    slug: str
    title: str
    difficulty: Difficulty
    tags: list[TagOut]
    acceptance_rate: float | None
    total_submissions: int
    status: Literal["SOLVED", "ATTEMPTED"] | None = None  # only for signed-in users


class ExampleOut(BaseModel):
    input: str
    output: str
    explanation: str | None


class ProblemPublic(BaseModel):
    """The cacheable, user-independent part of a problem. Never contains hidden tests or the editorial."""

    id: uuid.UUID
    slug: str
    title: str
    difficulty: Difficulty
    description: str
    constraints: str
    input_format: str
    output_format: str
    time_limit_ms: int
    memory_limit_mb: int
    function_signature: str | None
    tags: list[TagOut]
    examples: list[ExampleOut]
    hint_count: int
    starter_code: dict[str, str]
    acceptance_rate: float | None
    total_submissions: int


class ProblemDetail(ProblemPublic):
    status: Literal["SOLVED", "ATTEMPTED"] | None = None
    solution_unlocked: bool = False
    # Present only once the viewer has solved the problem (or is an admin).
    editorial: str | None = None
    expected_time_complexity: str | None = None
    expected_space_complexity: str | None = None


class HintOut(BaseModel):
    index: int
    total: int
    hint: str


# --- Admin --------------------------------------------------------------------------------------


class CaseInput(BaseModel):
    """A test case as submitted by an admin. `id` present = update that case; absent = create."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID | None = None
    kind: CaseKind
    input: str = Field(max_length=MAX_CASE_CHARS)
    expected_output: str = Field(max_length=MAX_CASE_CHARS)
    show_as_example: bool = False
    example_explanation: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _examples_are_public(self) -> CaseInput:
        if self.show_as_example and self.kind != CaseKind.PUBLIC:
            raise ValueError("only PUBLIC test cases can be shown as examples")
        return self


class ProblemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=120)
    slug: str = Field(min_length=3, max_length=80, pattern=SLUG_PATTERN)
    description: str = Field(max_length=30_000)
    difficulty: Difficulty
    constraints: str = Field(default="", max_length=10_000)
    input_format: str = Field(default="", max_length=10_000)
    output_format: str = Field(default="", max_length=10_000)
    time_limit_ms: int = Field(default=2000, ge=100, le=10_000)
    memory_limit_mb: int = Field(default=256, ge=16, le=1024)
    checker: CheckerName = "lines"
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS_PER_PROBLEM)
    hints: list[str] = Field(default_factory=list, max_length=MAX_HINTS)
    editorial: str | None = Field(default=None, max_length=50_000)
    function_signature: str | None = Field(default=None, max_length=300)
    expected_time_complexity: str | None = Field(default=None, max_length=60)
    expected_space_complexity: str | None = Field(default=None, max_length=60)
    starter_code: dict[str, str] = Field(default_factory=dict)
    test_cases: list[CaseInput] = Field(default_factory=list, max_length=MAX_TEST_CASES)

    @field_validator("hints")
    @classmethod
    def _hints(cls, value: list[str]) -> list[str]:
        cleaned = [hint.strip() for hint in value]
        if any(not hint for hint in cleaned):
            raise ValueError("hints cannot be blank")
        if any(len(hint) > 2000 for hint in cleaned):
            raise ValueError("each hint must be at most 2000 characters")
        return cleaned

    @field_validator("starter_code")
    @classmethod
    def _starter(cls, value: dict[str, str]) -> dict[str, str]:
        if any(len(code) > 20_000 for code in value.values()):
            raise ValueError("starter code is limited to 20000 characters per language")
        return value

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("tags must be unique")
        if any(not _SLUG_RE.match(tag) for tag in value):
            raise ValueError("tags are referenced by slug")
        return value


class CaseAdminOut(BaseModel):
    id: uuid.UUID
    kind: CaseKind
    input: str
    expected_output: str
    show_as_example: bool
    example_explanation: str | None


class ProblemAdminOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str
    difficulty: Difficulty
    constraints: str
    input_format: str
    output_format: str
    time_limit_ms: int
    memory_limit_mb: int
    checker: CheckerName
    tags: list[str]
    hints: list[str]
    editorial: str | None
    function_signature: str | None
    expected_time_complexity: str | None
    expected_space_complexity: str | None
    starter_code: dict[str, str]
    test_cases: list[CaseAdminOut]
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"]
    published_at: datetime | None
    total_submissions: int
    accepted_submissions: int
    created_at: datetime
    updated_at: datetime


class AdminProblemListItem(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    difficulty: Difficulty
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"]
    tags: list[str]
    public_tests: int
    hidden_tests: int
    total_submissions: int
    updated_at: datetime


class ValidationIssue(BaseModel):
    field: str
    code: str
    message: str


class ValidationReport(BaseModel):
    ok: bool
    issues: list[ValidationIssue]


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=40)
