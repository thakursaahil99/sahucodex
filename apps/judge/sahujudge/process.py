"""Runs a command on the *judge host side* (the `docker` CLI) with a hard time limit and bounded output.

This never runs user code: user code runs inside containers, driven through the CLI. It is bounded anyway because a
hung or chatty CLI must not hang or exhaust the worker.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    truncated: bool


async def _read_capped(stream: asyncio.StreamReader, cap: int, overflow: asyncio.Event) -> bytes:
    buffer = bytearray()
    while chunk := await stream.read(65536):
        room = cap - len(buffer)
        buffer += chunk[: max(room, 0)]
        if len(chunk) > room:
            overflow.set()
            break
    return bytes(buffer)


async def _feed(proc: asyncio.subprocess.Process, data: bytes) -> None:
    assert proc.stdin is not None
    with contextlib.suppress(BrokenPipeError, ConnectionResetError, OSError):
        proc.stdin.write(data)
        await proc.stdin.drain()
    with contextlib.suppress(BrokenPipeError, ConnectionResetError, OSError):
        proc.stdin.close()


async def run_command(
    argv: Sequence[str],
    *,
    stdin: bytes | None = None,
    timeout_s: float,
    max_output_bytes: int,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    """Runs `argv` (never through a shell). Kills the process on timeout or when its output exceeds the cap."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=dict(env) if env is not None else None,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None
    overflow = asyncio.Event()
    out_task = asyncio.ensure_future(_read_capped(proc.stdout, max_output_bytes, overflow))
    err_task = asyncio.ensure_future(_read_capped(proc.stderr, max_output_bytes, overflow))
    feed_task = asyncio.ensure_future(_feed(proc, stdin)) if stdin is not None else None
    watcher = asyncio.ensure_future(overflow.wait())
    everything = asyncio.ensure_future(
        asyncio.gather(out_task, err_task, *([feed_task] if feed_task else []), proc.wait())
    )

    timed_out = False
    try:
        # Finishes when the process has exited and its output is fully read, or as soon as the cap is exceeded.
        await asyncio.wait_for(asyncio.wait({everything, watcher}, return_when=asyncio.FIRST_COMPLETED), timeout_s)
    except TimeoutError:
        timed_out = True
    finally:
        watcher.cancel()
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
        if not everything.done():
            everything.cancel()
        # Collect the cancelled/finished readers without swallowing a cancellation of this coroutine itself.
        await asyncio.gather(everything, return_exceptions=True)

    def collected(task: asyncio.Future[bytes]) -> bytes:
        if task.done() and not task.cancelled() and task.exception() is None:
            return task.result()
        return b""

    return CommandResult(
        returncode=proc.returncode,
        stdout=collected(out_task),
        stderr=collected(err_task),
        timed_out=timed_out,
        truncated=overflow.is_set(),
    )
