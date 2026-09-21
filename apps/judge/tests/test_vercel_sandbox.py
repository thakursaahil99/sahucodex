"""VercelSession transport, with a fake microVM: no network, no Vercel account."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.core.config import Settings
from sahujudge.languages import get_language
from sahujudge.runtime import build_sandbox
from sahujudge.sandbox import SandboxError
from sahujudge.vercel_sandbox import (
    SUPERVISOR_REMOTE,
    VercelSandbox,
    VercelSandboxConfig,
    VercelSession,
    container_memory_mb,
)


@dataclass
class Done:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclass
class FakeFs:
    files: dict[str, bytes] = field(default_factory=dict)
    fail: Exception | None = None

    async def write_bytes(self, path: str, data: bytes, *, cwd: str | None = None) -> None:
        if self.fail:
            raise self.fail
        self.files[path] = data

    async def read_bytes(self, path: str, *, cwd: str | None = None) -> bytes:
        return self.files[path]


@dataclass
class FakeBox:
    name: str = "fake-vm"
    fs: FakeFs = field(default_factory=FakeFs)
    calls: list[tuple[str, list[str], dict[str, Any]]] = field(default_factory=list)
    result: Done = field(default_factory=Done)
    reply: bytes = b""

    async def run_process(self, command: str, args: list[str], **kwargs: Any) -> Done:
        self.calls.append((command, args, kwargs))
        # The command redirects supervisor stdout to a file; emulate that file appearing.
        script = args[-1]
        out_path = script.rsplit("> ", 1)[1]
        self.fs.files[out_path] = self.reply
        return self.result


def make_session(box: FakeBox) -> VercelSession:
    sandbox = VercelSandbox(VercelSandboxConfig(snapshot_id="snap_test"))
    return VercelSession(sandbox, box, get_language("python"), 128)


async def test_supervisor_call_feeds_stdin_from_a_file_and_returns_the_output_file() -> None:
    box = FakeBox(reply=b'{"status":"EXITED"}\nhello')
    session = make_session(box)

    result = await session._supervisor(["run", "--", "python3", "x y"], stdin=b"input", timeout_s=5, max_output=1000)

    command, args, kwargs = box.calls[0]
    script = args[-1]
    assert command == "sh" and args[0] == "-c"
    assert script.startswith(f"python3 {SUPERVISOR_REMOTE} run -- python3 'x y' < /tmp/sjx/in-")
    assert kwargs["kill_after"] == 5 and kwargs["cwd"] == "/"
    in_path = script.split("< ", 1)[1].split(" >", 1)[0]
    assert box.fs.files[in_path] == b"input"
    assert result.returncode == 0 and result.stdout == b'{"status":"EXITED"}\nhello'


async def test_arguments_are_shell_quoted_so_nothing_a_user_controls_becomes_a_command() -> None:
    box = FakeBox()
    session = make_session(box)

    await session._supervisor(["run", "--env", "A=$(reboot); b"], timeout_s=5, max_output=1000)

    assert "'A=$(reboot); b'" in box.calls[0][1][-1]


async def test_nonzero_supervisor_exit_is_a_sandbox_error() -> None:
    box = FakeBox(result=Done(returncode=2, stderr="boom"))
    with pytest.raises(SandboxError, match="boom"):
        await make_session(box)._supervisor(["run"], timeout_s=5, max_output=1000)


async def test_sdk_failures_become_sandbox_errors() -> None:
    box = FakeBox()
    box.fs.fail = RuntimeError("network down")
    with pytest.raises(SandboxError, match="Vercel Sandbox call failed"):
        await make_session(box)._supervisor(["run"], timeout_s=5, max_output=1000)


async def test_oversized_reply_is_a_sandbox_error() -> None:
    box = FakeBox(reply=b"x" * 50)
    with pytest.raises(SandboxError, match="did not finish"):
        await make_session(box)._supervisor(["run"], timeout_s=5, max_output=10)


def test_container_memory_leaves_room_for_the_compiler() -> None:
    assert container_memory_mb(get_language("cpp"), 64) == get_language("cpp").min_container_memory_mb
    assert container_memory_mb(get_language("python"), 512) == 576


def test_settings_pick_the_vercel_backend() -> None:
    settings = Settings(
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        jwt_secret="x" * 40,
        judge_backend="vercel",
        vercel_sandbox_snapshot="snap_abc",
        _env_file=None,
    )
    sandbox = build_sandbox(settings)
    assert isinstance(sandbox, VercelSandbox) and sandbox.config.snapshot_id == "snap_abc"
