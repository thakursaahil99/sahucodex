from __future__ import annotations

import pytest
from support import ScriptedSandbox, exited, killed

from sahujudge.checkers import (
    ExactChecker,
    LinesChecker,
    UnknownCheckerError,
    WhitespaceChecker,
    get_checker,
    register_checker,
)
from sahujudge.engine import JudgeConfig, JudgeTest, Verdict, judge_tests, order_tests, run_custom, verdict_for
from sahujudge.languages import LANGUAGES, get_language
from sahujudge.sandbox import CompileResult, RunStatus, SandboxError

# ---------------------------------------------------------------------------------------------------------------------
# checkers


@pytest.mark.parametrize(
    ("checker", "expected", "actual", "ok"),
    [
        (ExactChecker(), "1 2\n", "1 2\n", True),
        (ExactChecker(), "1 2\n", "1 2", False),  # a missing final newline is a difference for the strict checker
        (ExactChecker(), "1 2", "1  2", False),
        (WhitespaceChecker(), "1 2\n3", "1\t2   3\n\n", True),
        (WhitespaceChecker(), "1 2 3", "1 23", False),
        (WhitespaceChecker(), "", "  \n", True),
        (LinesChecker(), "1 2\n3\n", "1 2\n3", True),  # trailing newline forgiven
        (LinesChecker(), "1 2\r\n3\r\n", "1 2\n3\n", True),  # Windows line endings forgiven
        (LinesChecker(), "a\nb", "a  \nb\t\n\n\n", True),  # trailing whitespace and blank lines forgiven
        (LinesChecker(), "a\nb", "a\n\nb", False),  # a blank line in the middle is not
        (LinesChecker(), "a b", "a  b", False),  # inner spacing still matters for the line checker
        (LinesChecker(), " a", "a", False),  # so does leading whitespace
        (LinesChecker(), "a\nb", "b\na", False),
        (LinesChecker(), "", "\n\n", True),
        (LinesChecker(), "x", "", False),
    ],
)
def test_checkers(checker, expected, actual, ok) -> None:
    assert checker.check(expected, actual) is ok


def test_registry_and_extension() -> None:
    assert isinstance(get_checker("lines"), LinesChecker)
    with pytest.raises(UnknownCheckerError):
        get_checker("nope")

    class Numeric:
        name = "numeric-test"

        def check(self, expected: str, actual: str) -> bool:
            return abs(float(expected) - float(actual)) < 1e-6

    register_checker(Numeric())
    assert get_checker("numeric-test").check("0.1", "0.1000001") is True


# ---------------------------------------------------------------------------------------------------------------------
# verdict mapping

LINES = LinesChecker()


def test_verdict_mapping_is_exhaustive_and_ordered() -> None:
    assert verdict_for(exited("ok\n"), "ok", LINES)[0] is Verdict.ACCEPTED
    assert verdict_for(exited("no\n"), "ok", LINES)[0] is Verdict.WRONG_ANSWER
    assert verdict_for(killed(RunStatus.TIMEOUT), "ok", LINES)[0] is Verdict.TIME_LIMIT_EXCEEDED
    assert verdict_for(killed(RunStatus.MEMORY), "ok", LINES)[0] is Verdict.MEMORY_LIMIT_EXCEEDED
    assert verdict_for(killed(RunStatus.OUTPUT_LIMIT), "ok", LINES) == (Verdict.RUNTIME_ERROR, "Output limit exceeded")
    assert verdict_for(killed(RunStatus.SIGNALED, signal=11), "ok", LINES) == (
        Verdict.RUNTIME_ERROR,
        "Terminated by SIGSEGV",
    )
    assert verdict_for(exited("ok", code=3), "ok", LINES) == (Verdict.RUNTIME_ERROR, "Exited with code 3")


def test_a_correct_looking_output_never_rescues_a_failed_run() -> None:
    """Matching stdout with a non-zero exit, a timeout or a memory kill must not be ACCEPTED."""
    good = exited("42\n", code=1)
    assert verdict_for(good, "42", LINES)[0] is Verdict.RUNTIME_ERROR
    timed_out = killed(RunStatus.TIMEOUT)
    assert verdict_for(timed_out, "", LINES)[0] is Verdict.TIME_LIMIT_EXCEEDED


def test_every_verdict_matches_the_api_enum() -> None:
    from app.modules.submissions.models import Verdict as ApiVerdict

    assert {v.value for v in Verdict} == {v.value for v in ApiVerdict}


# ---------------------------------------------------------------------------------------------------------------------
# judge_tests

PY = get_language("python")


def make_tests(*pairs: tuple[str, str, bool]) -> list[JudgeTest]:
    return [JudgeTest(input=i, expected=o, public=p, id=f"t{n}") for n, (i, o, p) in enumerate(pairs)]


def echo_upper(stdin: str):
    return exited(stdin.upper())


async def test_accepted_runs_every_test() -> None:
    sandbox = ScriptedSandbox(echo_upper)
    tests = make_tests(("a", "A", True), ("b", "B", False), ("c", "C", False))
    report = await judge_tests(
        sandbox, language=PY, source="x", tests=tests, time_limit_ms=1000, memory_limit_mb=64, checker=LINES
    )
    assert (report.verdict, report.passed, report.total) == (Verdict.ACCEPTED, 3, 3)
    assert sandbox.sessions_opened == sandbox.sessions_closed == 1  # one sandbox for the whole submission, closed


async def test_stops_at_the_first_failure_and_reports_partial_progress() -> None:
    sandbox = ScriptedSandbox(lambda stdin: exited("WRONG" if stdin == "b" else stdin.upper()))
    tests = make_tests(("a", "A", True), ("b", "B", False), ("c", "C", False))
    report = await judge_tests(
        sandbox, language=PY, source="x", tests=tests, time_limit_ms=1000, memory_limit_mb=64, checker=LINES
    )
    assert (report.verdict, report.passed, report.total) == (Verdict.WRONG_ANSWER, 1, 3)
    assert sandbox.inputs == ["a", "b"]  # "c" was never executed


async def test_public_tests_run_before_hidden_ones_regardless_of_input_order() -> None:
    tests = make_tests(("h1", "", False), ("p1", "", True), ("h2", "", False), ("p2", "", True))
    assert [t.input for t in order_tests(tests)] == ["p1", "p2", "h1", "h2"]


async def test_verdict_is_the_first_failure_in_execution_order() -> None:
    def respond(stdin: str):
        return {"a": exited("A"), "b": killed(RunStatus.TIMEOUT), "c": exited("nope")}[stdin]

    tests = make_tests(("a", "A", True), ("b", "B", False), ("c", "C", False))
    report = await judge_tests(
        ScriptedSandbox(respond),
        language=PY,
        source="x",
        tests=tests,
        time_limit_ms=1000,
        memory_limit_mb=64,
        checker=LINES,
        stop_on_failure=False,
    )
    assert report.verdict is Verdict.TIME_LIMIT_EXCEEDED  # not the later WRONG_ANSWER
    assert [o.verdict for o in report.outcomes] == [Verdict.ACCEPTED, Verdict.TIME_LIMIT_EXCEEDED, Verdict.WRONG_ANSWER]


async def test_the_judge_is_deterministic() -> None:
    tests = make_tests(("a", "A", True), ("b", "X", False))

    async def once():
        report = await judge_tests(
            ScriptedSandbox(echo_upper),
            language=PY,
            source="x",
            tests=tests,
            time_limit_ms=1000,
            memory_limit_mb=64,
            checker=LINES,
        )
        return report.verdict, report.passed, report.total, report.message

    assert len({await once() for _ in range(5)}) == 1


async def test_compilation_error_runs_nothing_and_reports_the_compiler_output() -> None:
    sandbox = ScriptedSandbox(echo_upper, compile_result=CompileResult(ok=False, output="main.cpp:1: error: boom"))
    report = await judge_tests(
        sandbox,
        language=get_language("cpp"),
        source="x",
        tests=make_tests(("a", "A", True)),
        time_limit_ms=1000,
        memory_limit_mb=64,
        checker=LINES,
    )
    assert report.verdict is Verdict.COMPILATION_ERROR
    assert report.compile_output == "main.cpp:1: error: boom"
    assert sandbox.inputs == []
    assert sandbox.sessions_closed == 1


async def test_hidden_test_data_is_never_retained_even_when_capturing() -> None:
    secret_in, secret_out = "SECRET-INPUT-123", "SECRET-OUTPUT-456"
    sandbox = ScriptedSandbox(lambda stdin: exited("printed: " + stdin, stderr="trace mentioning " + stdin, code=1))
    tests = [JudgeTest(input="public-in", expected="public-out", public=True, id="p")]
    tests += [JudgeTest(input=secret_in, expected=secret_out, public=False, id="h")]
    report = await judge_tests(
        sandbox,
        language=PY,
        source="x",
        tests=tests,
        time_limit_ms=1000,
        memory_limit_mb=64,
        checker=LINES,
        stop_on_failure=False,
        capture_public=True,
    )
    hidden = next(o for o in report.outcomes if not o.public)
    public = next(o for o in report.outcomes if o.public)
    assert (hidden.input, hidden.expected, hidden.stdout, hidden.stderr, hidden.message) == (None,) * 5
    assert public.input == "public-in"
    assert public.stdout == "printed: public-in"
    blob = repr(report)
    assert secret_in not in blob
    assert secret_out not in blob


async def test_submit_mode_keeps_no_output_at_all() -> None:
    report = await judge_tests(
        ScriptedSandbox(echo_upper),
        language=PY,
        source="x",
        tests=make_tests(("a", "A", True)),
        time_limit_ms=1000,
        memory_limit_mb=64,
        checker=LINES,
    )
    assert all(o.stdout is None and o.input is None for o in report.outcomes)


async def test_sandbox_failure_propagates_and_is_not_a_verdict() -> None:
    sandbox = ScriptedSandbox(echo_upper, fail_on_open=SandboxError("daemon down"))
    with pytest.raises(SandboxError):
        await judge_tests(
            sandbox,
            language=PY,
            source="x",
            tests=make_tests(("a", "A", True)),
            time_limit_ms=1000,
            memory_limit_mb=64,
            checker=LINES,
        )


async def test_sandbox_is_closed_when_a_run_raises() -> None:
    def boom(_: str):
        raise SandboxError("supervisor died")

    sandbox = ScriptedSandbox(boom)
    with pytest.raises(SandboxError):
        await judge_tests(
            sandbox,
            language=PY,
            source="x",
            tests=make_tests(("a", "A", True)),
            time_limit_ms=1000,
            memory_limit_mb=64,
            checker=LINES,
        )
    assert sandbox.sessions_closed == 1


async def test_language_multiplier_scales_the_limit_and_config_flows_into_run_limits() -> None:
    sandbox = ScriptedSandbox(echo_upper)
    config = JudgeConfig(max_output_bytes=123, max_stderr_bytes=45)
    await judge_tests(
        sandbox,
        language=PY,
        source="x",
        tests=make_tests(("a", "A", True)),
        time_limit_ms=1000,
        memory_limit_mb=64,
        checker=LINES,
        config=config,
    )
    limits = sandbox.limits[0]
    assert limits.time_ms == int(1000 * PY.time_multiplier)
    assert limits.wall_ms > limits.time_ms
    assert (limits.max_output_bytes, limits.max_stderr_bytes, limits.memory_mb) == (123, 45, 64)


async def test_too_many_tests_is_refused_before_anything_runs() -> None:
    sandbox = ScriptedSandbox(echo_upper)
    with pytest.raises(ValueError, match="too many"):
        await judge_tests(
            sandbox,
            language=PY,
            source="x",
            tests=make_tests(*[("a", "A", True)] * 5),
            time_limit_ms=1000,
            memory_limit_mb=64,
            checker=LINES,
            config=JudgeConfig(max_tests=2),
        )
    assert sandbox.sessions_opened == 0


async def test_run_custom_maps_outcomes_without_an_expected_output() -> None:
    async def go(result):
        return await run_custom(
            ScriptedSandbox(lambda _: result),
            language=PY,
            source="x",
            stdin="in",
            time_limit_ms=1000,
            memory_limit_mb=64,
        )

    ok = await go(exited("hello", stderr="warn"))
    assert (ok.status, ok.stdout, ok.stderr) == ("OK", "hello", "warn")
    assert (await go(killed(RunStatus.TIMEOUT))).status == "TIME_LIMIT_EXCEEDED"
    assert (await go(killed(RunStatus.MEMORY))).status == "MEMORY_LIMIT_EXCEEDED"
    crashed = await go(exited("", code=2))
    assert (crashed.status, crashed.message) == ("RUNTIME_ERROR", "Exited with code 2")


def test_language_table_is_complete_and_uses_fixed_argv() -> None:
    assert set(LANGUAGES) == {
        "python",
        "cpp",
        "javascript",
        "c",
        "java",
        "csharp",
        "go",
        "rust",
        "typescript",
        "php",
    }
    for spec in LANGUAGES.values():
        for command in (spec.compile, spec.run):
            assert command is None or all(isinstance(part, str) for part in command)
        assert spec.source_path.startswith("/work/")
    assert "-O2" in LANGUAGES["cpp"].compile
    with pytest.raises(LookupError):
        get_language("cobol")
