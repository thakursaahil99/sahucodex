"""Test doubles. They live in `tests/` and are never imported by product code.

* `ScriptedSandbox` returns whatever a test function decides, to exercise verdict logic in isolation.
* `TrustedLocalSandbox` runs *trusted Python snippets written by this test suite* in a plain subprocess, so the pipeline
  (queue -> verdict -> database -> events) can be tested end to end on a machine without Docker. It provides NO
  isolation and refuses anything but Python; it exists only to run code the tests themselves wrote.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from sahujudge.languages import LanguageSpec
from sahujudge.sandbox import CompileResult, RunLimits, RunResult, RunStatus


def exited(stdout: str = "", *, code: int = 0, time_ms: int = 10, memory_kb: int = 4096, stderr: str = "") -> RunResult:
    return RunResult(
        status=RunStatus.EXITED,
        exit_code=code,
        signal=None,
        time_ms=time_ms,
        wall_ms=time_ms,
        memory_kb=memory_kb,
        stdout=stdout,
        stderr=stderr,
    )


def killed(status: RunStatus, *, signal: int | None = 9, time_ms: int = 50, memory_kb: int = 4096) -> RunResult:
    return RunResult(
        status=status,
        exit_code=None,
        signal=signal,
        time_ms=time_ms,
        wall_ms=time_ms,
        memory_kb=memory_kb,
        stdout="",
        stderr="",
    )


class ScriptedSandbox:
    def __init__(
        self,
        respond: Callable[[str], RunResult],
        *,
        compile_result: CompileResult | None = None,
        fail_on_open: Exception | None = None,
    ) -> None:
        self.respond = respond
        self.compile_result = compile_result or CompileResult(ok=True, output="")
        self.fail_on_open = fail_on_open
        self.sessions_opened = 0
        self.sessions_closed = 0
        self.inputs: list[str] = []
        self.memory_limits: list[int] = []
        self.limits: list[RunLimits] = []

    @asynccontextmanager
    async def session(self, language: LanguageSpec, source: str, *, memory_limit_mb: int) -> AsyncIterator[object]:
        if self.fail_on_open:
            raise self.fail_on_open
        self.sessions_opened += 1
        self.memory_limits.append(memory_limit_mb)
        outer = self

        class Session:
            async def compile(self) -> CompileResult:
                return outer.compile_result

            async def run(self, stdin: str, limits: RunLimits) -> RunResult:
                outer.inputs.append(stdin)
                outer.limits.append(limits)
                return outer.respond(stdin)

        try:
            yield Session()
        finally:
            self.sessions_closed += 1


class TrustedLocalSandbox:
    def __init__(self, *, i_understand_this_runs_code_without_isolation: bool) -> None:
        assert i_understand_this_runs_code_without_isolation
        self.sessions_opened = 0

    @asynccontextmanager
    async def session(self, language: LanguageSpec, source: str, *, memory_limit_mb: int) -> AsyncIterator[object]:
        assert language.key == "python", "the trusted local double only runs Python written by the test suite"
        self.sessions_opened += 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.py"
            path.write_text(source, encoding="utf-8")

            class Session:
                async def compile(self) -> CompileResult:
                    proc = await asyncio.to_thread(
                        subprocess.run, [sys.executable, "-m", "py_compile", str(path)], capture_output=True, text=True
                    )
                    return CompileResult(ok=proc.returncode == 0, output=proc.stderr[-2000:])

                async def run(self, stdin: str, limits: RunLimits) -> RunResult:
                    started = time.monotonic()
                    try:
                        proc = await asyncio.to_thread(
                            subprocess.run,
                            [sys.executable, str(path)],
                            input=stdin,
                            capture_output=True,
                            text=True,
                            timeout=limits.wall_ms / 1000,
                            cwd=directory,
                        )
                    except subprocess.TimeoutExpired:
                        return killed(RunStatus.TIMEOUT, time_ms=limits.time_ms + 1)
                    elapsed = int((time.monotonic() - started) * 1000)
                    return exited(
                        proc.stdout[: limits.max_output_bytes],
                        code=proc.returncode,
                        time_ms=elapsed,
                        stderr=proc.stderr[: limits.max_stderr_bytes],
                    )

            yield Session()
