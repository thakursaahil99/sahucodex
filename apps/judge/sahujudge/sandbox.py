"""What the judge needs from a sandbox, independent of how it is implemented.

`docker_sandbox.DockerSandbox` is the production implementation. Tests substitute in-memory doubles for the *engine*
tests; nothing in the product ever runs user code outside a sandbox.
"""

from __future__ import annotations

import enum
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from sahujudge.languages import LanguageSpec


class SandboxError(RuntimeError):
    """The sandbox itself failed (daemon down, image missing, supervisor misbehaved). Never a user's fault, so it is
    reported as SYSTEM_ERROR and never counted as an attempt."""


class RunStatus(enum.StrEnum):
    EXITED = "EXITED"  # the program ended by itself (any exit code)
    TIMEOUT = "TIMEOUT"  # CPU or wall-clock limit
    MEMORY = "MEMORY"  # memory limit (resident-set check or the kernel's OOM killer)
    OUTPUT_LIMIT = "OUTPUT_LIMIT"  # wrote more than the output cap
    SIGNALED = "SIGNALED"  # killed by a signal it did not cause us to send (SIGSEGV, SIGABRT, ...)


@dataclass(frozen=True)
class RunLimits:
    time_ms: int  # CPU time
    wall_ms: int
    memory_mb: int
    max_output_bytes: int
    max_stderr_bytes: int
    stack_mb: int = 64
    # Open-file-descriptor cap (RLIMIT_NOFILE). 128 is plenty for a submission's own process and blocks fork-bomb-style
    # descriptor exhaustion; some compiler toolchains (observed: .NET's MSBuild) open far more than that just to start
    # up and fail in confusing ways (OOM-killed, "assembly not found") well under their CPU/wall/memory limits. Only
    # `compile()` ever raises this, via `LanguageSpec.compile_nofile_limit`; user code still runs under 128.
    nofile: int = 128


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    exit_code: int | None
    signal: int | None
    time_ms: int
    wall_ms: int
    memory_kb: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class CompileResult:
    ok: bool
    output: str


class SandboxSession(Protocol):
    async def compile(self) -> CompileResult: ...

    async def run(self, stdin: str, limits: RunLimits) -> RunResult: ...


class Sandbox(Protocol):
    def session(
        self, language: LanguageSpec, source: str, *, memory_limit_mb: int
    ) -> AbstractAsyncContextManager[SandboxSession]:
        """Creates an isolated environment holding `source`, destroyed when the context exits however it exits."""
        ...
