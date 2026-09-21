"""Turns sandbox executions into verdicts. Pure logic over the `Sandbox` interface: no database, no queue.

Rules, in the order they are applied to each test:

1. The program is killed for exceeding its CPU/wall time      -> TIME_LIMIT_EXCEEDED
2. ... its memory                                              -> MEMORY_LIMIT_EXCEEDED
3. ... its output cap, exits non-zero, or dies from a signal   -> RUNTIME_ERROR
4. Otherwise its stdout is compared with the expected output   -> ACCEPTED or WRONG_ANSWER

Tests run in a fixed order (public before hidden, then by position) and stop at the first failure, so the same code
and tests always give the same verdict. A failure of the sandbox itself raises `SandboxError`, which the caller
reports as SYSTEM_ERROR; it is never converted into a verdict about the user's code.

What leaves this module is decided here: for hidden tests only verdict, runtime and memory are kept. The program's
output, its stderr and the test data are retained solely for PUBLIC tests, and only when the caller asks.
"""

from __future__ import annotations

import enum
import signal as signal_module
from collections.abc import Sequence
from dataclasses import dataclass, field

from sahujudge.checkers import Checker
from sahujudge.languages import LanguageSpec
from sahujudge.sandbox import RunLimits, RunResult, RunStatus, Sandbox


class Verdict(enum.StrEnum):
    ACCEPTED = "ACCEPTED"
    WRONG_ANSWER = "WRONG_ANSWER"
    TIME_LIMIT_EXCEEDED = "TIME_LIMIT_EXCEEDED"
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"


@dataclass(frozen=True)
class JudgeTest:
    input: str
    expected: str
    public: bool
    id: str | None = None


@dataclass(frozen=True)
class JudgeConfig:
    max_output_bytes: int = 1_048_576
    max_stderr_bytes: int = 8_192
    max_tests: int = 200
    stack_mb: int = 64


@dataclass
class CaseOutcome:
    position: int  # 1-based execution order
    test_id: str | None
    public: bool
    verdict: Verdict
    time_ms: int | None
    memory_kb: int | None
    message: str | None = None
    # Populated only for PUBLIC tests and only when `capture_public` is set (the Run button).
    input: str | None = None
    expected: str | None = None
    stdout: str | None = None
    stderr: str | None = None


@dataclass
class JudgeReport:
    verdict: Verdict
    total: int
    passed: int = 0
    compile_output: str | None = None
    message: str | None = None
    runtime_ms: int | None = None
    memory_kb: int | None = None
    outcomes: list[CaseOutcome] = field(default_factory=list)


def effective_time_limit_ms(problem_limit_ms: int, language: LanguageSpec) -> int:
    return int(problem_limit_ms * language.time_multiplier)


def limits_for(time_limit_ms: int, memory_limit_mb: int, config: JudgeConfig) -> RunLimits:
    return RunLimits(
        time_ms=time_limit_ms,
        wall_ms=time_limit_ms * 2 + 1000,
        memory_mb=memory_limit_mb,
        max_output_bytes=config.max_output_bytes,
        max_stderr_bytes=config.max_stderr_bytes,
        stack_mb=config.stack_mb,
    )


def describe_termination(result: RunResult) -> str:
    if result.status is RunStatus.OUTPUT_LIMIT:
        return "Output limit exceeded"
    if result.signal is not None:
        try:
            name = signal_module.Signals(result.signal).name
        except ValueError:
            name = f"signal {result.signal}"
        return f"Terminated by {name}"
    return f"Exited with code {result.exit_code}"


def verdict_for(result: RunResult, expected: str, checker: Checker) -> tuple[Verdict, str | None]:
    """Maps one execution to a verdict. Deterministic: depends only on its arguments."""
    if result.status is RunStatus.TIMEOUT:
        return Verdict.TIME_LIMIT_EXCEEDED, None
    if result.status is RunStatus.MEMORY:
        return Verdict.MEMORY_LIMIT_EXCEEDED, None
    if result.status is not RunStatus.EXITED or result.exit_code != 0:
        return Verdict.RUNTIME_ERROR, describe_termination(result)
    if checker.check(expected, result.stdout):
        return Verdict.ACCEPTED, None
    return Verdict.WRONG_ANSWER, None


def order_tests(tests: Sequence[JudgeTest]) -> list[JudgeTest]:
    """Public tests first, otherwise the caller's order (stable), so the first failure is well defined."""
    return sorted(tests, key=lambda test: not test.public)


async def judge_tests(
    sandbox: Sandbox,
    *,
    language: LanguageSpec,
    source: str,
    tests: Sequence[JudgeTest],
    time_limit_ms: int,
    memory_limit_mb: int,
    checker: Checker,
    config: JudgeConfig | None = None,
    stop_on_failure: bool = True,
    capture_public: bool = False,
) -> JudgeReport:
    """Compiles once, then runs `tests` in order.

    `time_limit_ms` is the problem's own; the language multiplier is applied here."""
    config = config or JudgeConfig()
    ordered = order_tests(tests)
    if len(ordered) > config.max_tests:
        raise ValueError(f"too many tests ({len(ordered)} > {config.max_tests})")
    limits = limits_for(effective_time_limit_ms(time_limit_ms, language), memory_limit_mb, config)
    report = JudgeReport(verdict=Verdict.ACCEPTED, total=len(ordered))

    async with sandbox.session(language, source, memory_limit_mb=memory_limit_mb) as session:
        compiled = await session.compile()
        if not compiled.ok:
            report.verdict = Verdict.COMPILATION_ERROR
            report.compile_output = compiled.output
            return report

        for position, test in enumerate(ordered, start=1):
            result = await session.run(test.input, limits)
            verdict, message = verdict_for(result, test.expected, checker)
            outcome = CaseOutcome(
                position=position,
                test_id=test.id,
                public=test.public,
                verdict=verdict,
                time_ms=result.time_ms,
                memory_kb=result.memory_kb,
            )
            if test.public:  # stderr and output are only ever kept for tests the user can already see
                outcome.message = message
                if capture_public:
                    outcome.input = test.input
                    outcome.expected = test.expected
                    outcome.stdout = result.stdout
                    outcome.stderr = result.stderr
            report.outcomes.append(outcome)
            report.runtime_ms = max(report.runtime_ms or 0, result.time_ms)
            report.memory_kb = max(report.memory_kb or 0, result.memory_kb)

            if verdict is Verdict.ACCEPTED:
                report.passed += 1
                continue
            if report.verdict is Verdict.ACCEPTED:  # the first failure decides the submission's verdict
                report.verdict = verdict
                report.message = message
            if stop_on_failure:
                break
    return report


@dataclass
class CustomRunReport:
    """Result of running the user's program on input they supplied. There is no expected output, so no WRONG_ANSWER."""

    status: str  # "OK" or a Verdict value
    compile_output: str | None = None
    stdout: str = ""
    stderr: str = ""
    message: str | None = None
    time_ms: int | None = None
    memory_kb: int | None = None


async def run_custom(
    sandbox: Sandbox,
    *,
    language: LanguageSpec,
    source: str,
    stdin: str,
    time_limit_ms: int,
    memory_limit_mb: int,
    config: JudgeConfig | None = None,
) -> CustomRunReport:
    config = config or JudgeConfig()
    limits = limits_for(effective_time_limit_ms(time_limit_ms, language), memory_limit_mb, config)
    async with sandbox.session(language, source, memory_limit_mb=memory_limit_mb) as session:
        compiled = await session.compile()
        if not compiled.ok:
            return CustomRunReport(status=Verdict.COMPILATION_ERROR, compile_output=compiled.output)
        result = await session.run(stdin, limits)
    report = CustomRunReport(
        status="OK",
        stdout=result.stdout,
        stderr=result.stderr,
        time_ms=result.time_ms,
        memory_kb=result.memory_kb,
    )
    if result.status is RunStatus.TIMEOUT:
        report.status = Verdict.TIME_LIMIT_EXCEEDED
    elif result.status is RunStatus.MEMORY:
        report.status = Verdict.MEMORY_LIMIT_EXCEEDED
    elif result.status is not RunStatus.EXITED or result.exit_code != 0:
        report.status = Verdict.RUNTIME_ERROR
        report.message = describe_termination(result)
    return report
