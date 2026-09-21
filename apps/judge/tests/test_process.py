"""The bounded subprocess runner, against real subprocesses (a Python one-liner stands in for the docker CLI)."""

from __future__ import annotations

import sys
import time

from sahujudge.process import run_command

PY = sys.executable


async def test_captures_output_exit_code_and_feeds_stdin() -> None:
    code = (
        "import sys; data = sys.stdin.read(); print(data.upper(), end=''); print('warn', file=sys.stderr); sys.exit(3)"
    )
    result = await run_command([PY, "-c", code], stdin=b"hello", timeout_s=20, max_output_bytes=1000)
    assert (result.returncode, result.stdout, result.stderr.strip()) == (3, b"HELLO", b"warn")
    assert not result.timed_out
    assert not result.truncated


async def test_a_hung_process_is_killed_at_the_timeout() -> None:
    started = time.monotonic()
    result = await run_command([PY, "-c", "import time; time.sleep(60)"], timeout_s=0.5, max_output_bytes=1000)
    assert result.timed_out
    assert time.monotonic() - started < 10
    assert result.returncode != 0


async def test_a_flood_of_output_is_cut_off_and_the_process_killed() -> None:
    flood = "import sys\nwhile True:\n    sys.stdout.write('x' * 65536)\n    sys.stdout.flush()"
    started = time.monotonic()
    result = await run_command([PY, "-c", flood], timeout_s=30, max_output_bytes=10_000)
    assert result.truncated
    assert len(result.stdout) <= 10_000
    assert result.returncode != 0
    assert time.monotonic() - started < 20


async def test_a_process_that_ignores_stdin_does_not_block() -> None:
    result = await run_command([PY, "-c", "print('done')"], stdin=b"x" * 5_000_000, timeout_s=30, max_output_bytes=1000)
    assert result.stdout.strip() == b"done"


async def test_a_missing_executable_raises_rather_than_hanging() -> None:
    import pytest

    with pytest.raises(FileNotFoundError):
        await run_command(["definitely-not-a-real-binary-xyz"], timeout_s=5, max_output_bytes=100)
