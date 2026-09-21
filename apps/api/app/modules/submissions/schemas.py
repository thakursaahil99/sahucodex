"""Request and response models for SahuJudge.

Nothing here can carry a hidden test: there is no field for test input, expected output or a program's output on a
hidden test. Per-test rows are exposed only for PUBLIC tests, which the statement already shows.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.submissions.models import SubmissionStatus, Verdict

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
LANGUAGE_PATTERN = r"^[a-z0-9_+-]{1,20}$"
# A hard ceiling for parsing only; the configured byte limit (SUBMISSION_MAX_SOURCE_BYTES) is checked in the service.
MAX_SOURCE_CHARS = 200_000


class SubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_slug: str = Field(max_length=80, pattern=SLUG_PATTERN)
    language: str = Field(pattern=LANGUAGE_PATTERN)
    source_code: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_slug: str = Field(max_length=80, pattern=SLUG_PATTERN)
    language: str = Field(pattern=LANGUAGE_PATTERN)
    source_code: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)
    mode: Literal["samples", "custom"] = "samples"
    input: str | None = Field(default=None, max_length=MAX_SOURCE_CHARS, description="stdin, for mode=custom")


class SubmissionQueued(BaseModel):
    id: uuid.UUID
    status: SubmissionStatus


class PublicTestResult(BaseModel):
    position: int
    verdict: Verdict
    runtime_ms: int | None
    memory_kb: int | None


class SubmissionSummary(BaseModel):
    id: uuid.UUID
    problem_slug: str
    problem_title: str
    language: str
    status: SubmissionStatus
    verdict: Verdict | None
    runtime_ms: int | None
    memory_kb: int | None
    passed_count: int
    total_count: int
    created_at: datetime
    finished_at: datetime | None


class SubmissionDetail(SubmissionSummary):
    source_code: str
    compile_output: str | None
    message: str | None
    time_limit_ms: int | None
    memory_limit_mb: int | None
    test_results: list[PublicTestResult]


class RunQueued(BaseModel):
    id: str
    status: Literal["QUEUED"] = "QUEUED"


class RunCaseOut(BaseModel):
    """One PUBLIC test from the statement, run against the user's code."""

    position: int
    verdict: Verdict
    input: str
    expected_output: str
    stdout: str
    stderr: str
    message: str | None
    runtime_ms: int | None
    memory_kb: int | None


class RunResultOut(BaseModel):
    outcome: str  # "OK" (custom run finished), or a Verdict value
    compile_output: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    message: str | None = None
    runtime_ms: int | None = None
    memory_kb: int | None = None
    cases: list[RunCaseOut] | None = None


class RunOut(BaseModel):
    id: str
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
    mode: Literal["samples", "custom"]
    result: RunResultOut | None = None
    error: str | None = None


class WsTicket(BaseModel):
    ticket: str
    expires_in: int
