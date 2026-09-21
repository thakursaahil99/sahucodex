"""Docker backend logic, tested without a daemon: exact argv, lifecycle and cleanup, and reply parsing.

These prove *what we ask Docker to do*. That the kernel then enforces it is proven by test_docker_integration.py, which
needs a real daemon.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from sahujudge.docker_sandbox import (
    DockerSandbox,
    DockerSandboxConfig,
    build_exec_argv,
    build_run_argv,
    container_memory_mb,
    docker_env,
    parse_supervisor_output,
)
from sahujudge.languages import get_language
from sahujudge.process import CommandResult
from sahujudge.sandbox import RunLimits, RunStatus, SandboxError

CONFIG = DockerSandboxConfig(docker_host="tcp://sandbox:2375")
LIMITS = RunLimits(time_ms=1000, wall_ms=3000, memory_mb=64, max_output_bytes=1000, max_stderr_bytes=100)


def flag_value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


# --- the container we ask for -------------------------------------------------------------------------------------------


def test_run_argv_carries_every_isolation_control() -> None:
    argv = build_run_argv(CONFIG, "sjx-test", 256, created_at=1)
    assert flag_value(argv, "--network") == "none"
    assert "--read-only" in argv
    assert flag_value(argv, "--cap-drop") == "ALL"
    assert flag_value(argv, "--security-opt") == "no-new-privileges"
    assert flag_value(argv, "--pids-limit") == "64"
    assert flag_value(argv, "--memory") == flag_value(argv, "--memory-swap") == "256m"  # no swap
    assert flag_value(argv, "--cpus") == "1.0"
    assert flag_value(argv, "--user") == "10002:10002"  # not root, and not the user that runs submitted code
    assert "--rm" in argv
    assert flag_value(argv, "--log-driver") == "none"
    # Only tmpfs is writable, and /tmp is not executable.
    tmpfs = [argv[i + 1] for i, part in enumerate(argv) if part == "--tmpfs"]
    assert len(tmpfs) == 2
    work = next(t for t in tmpfs if t.startswith("/work:"))
    tmp = next(t for t in tmpfs if t.startswith("/tmp:"))
    assert "exec" in work.split(":")[1].split(",")
    assert "noexec" in tmp
    assert "nosuid" in work
    assert "uid=10001" in work
    assert argv[-5:-2] == ["python3", "/opt/sjx/supervisor.py", "idle"]  # main process is the self-destructing idler


FORBIDDEN_FLAGS = {
    "--privileged",
    "--volume",
    "-v",
    "--mount",
    "--device",
    "--cap-add",
    "--pid",
    "--ipc",
    "--userns",
    "--publish",
    "-p",
    "--publish-all",
    "--add-host",
    "--volumes-from",
    "--env-file",
}


@pytest.mark.parametrize("runtime", [None, "runsc"])
def test_run_argv_can_never_express_a_mount_a_port_or_privileges(runtime) -> None:
    config = DockerSandboxConfig(runtime=runtime)
    argv = build_run_argv(config, "sjx-x", 128, created_at=1)
    assert not FORBIDDEN_FLAGS & set(argv)
    joined = " ".join(argv)
    assert "docker.sock" not in joined
    assert "--network host" not in joined
    assert ("--runtime" in argv) is bool(runtime)
    # The only --env is our own marker; no secret can ride along.
    envs = [argv[i + 1] for i, part in enumerate(argv) if part == "--env"]
    assert envs == ["SJX_SANDBOX=1"]


def test_exec_argv_runs_as_the_user_account_in_the_work_dir() -> None:
    argv = build_exec_argv(CONFIG, "sjx-x", ["run", "--time-ms", "5"])
    assert argv[:2] == ["docker", "exec"]
    assert flag_value(argv, "--user") == "10001:10001"
    assert "--privileged" not in argv
    assert argv[-3:] == ["run", "--time-ms", "5"]


def test_memory_is_sized_for_the_compiler_but_never_below_the_problem_limit() -> None:
    cpp, py = get_language("cpp"), get_language("python")
    assert container_memory_mb(CONFIG, cpp, 16) == cpp.min_container_memory_mb
    assert container_memory_mb(CONFIG, py, 512) == 512 + CONFIG.memory_slack_mb


def test_the_docker_cli_does_not_inherit_worker_secrets(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:hunter2@db/x")
    monkeypatch.setenv("JWT_SECRET", "s3cret")
    monkeypatch.setenv("REDIS_URL", "redis://:pw@redis")
    env = docker_env(CONFIG)
    assert env["DOCKER_HOST"] == "tcp://sandbox:2375"
    assert not {"DATABASE_URL", "JWT_SECRET", "REDIS_URL"} & set(env)
    assert "PATH" in env or os.name == "nt"


# --- reply parsing ------------------------------------------------------------------------------------------------------


def reply(status="EXITED", out=b"hi\n", err=b"", **overrides) -> bytes:
    header = {
        "status": status,
        "exit_code": 0,
        "signal": None,
        "cpu_ms": 12,
        "wall_ms": 20,
        "memory_kb": 5000,
        "stdout_len": len(out),
        "stderr_len": len(err),
    }
    header.update(overrides)
    return json.dumps(header).encode() + b"\n" + out + err


def test_parse_splits_stdout_and_stderr_by_declared_length() -> None:
    header, out, err = parse_supervisor_output(reply(out=b"a\nb\n", err=b"oops"))
    assert (out, err, header["cpu_ms"]) == (b"a\nb\n", b"oops", 12)


def test_a_program_printing_a_fake_header_cannot_forge_one() -> None:
    forged = b'{"status":"EXITED","exit_code":0,"stdout_len":0,"stderr_len":0,"cpu_ms":0,"wall_ms":0,"memory_kb":0}\n'
    _, out, _ = parse_supervisor_output(reply(out=forged + b"junk"))
    assert out.startswith(b'{"status"')  # it is just program output, compared like any other output


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not json\nbody",
        reply(stdout_len=999),  # lengths must add up to the body exactly
        reply(status="ACCEPTED"),  # the supervisor may only report run statuses, never verdicts
        reply(cpu_ms="0"),
        reply(stdout_len=-1, stderr_len=4),
        b"[1,2,3]\nbody",
    ],
)
def test_malformed_replies_are_sandbox_errors_not_verdicts(raw) -> None:
    with pytest.raises(SandboxError):
        parse_supervisor_output(raw)


# --- lifecycle, with a fake docker CLI ----------------------------------------------------------------------------------


class FakeDocker:
    """Records every docker invocation and answers like a healthy daemon unless told otherwise."""

    def __init__(self, *, run_code: int = 0, exec_replies: list[bytes] | None = None, hang_exec: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.stdins: list[bytes | None] = []
        self.run_code = run_code
        self.exec_replies = list(exec_replies or [])
        self.hang_exec = hang_exec

    async def __call__(self, argv, *, stdin=None, timeout_s, max_output_bytes, env=None) -> CommandResult:
        self.calls.append(list(argv))
        self.stdins.append(stdin)
        verb = argv[1]
        if verb == "run":
            return CommandResult(self.run_code, b"container-id\n", b"boom" if self.run_code else b"", False, False)
        if verb == "exec":
            if self.hang_exec:
                await asyncio.sleep(3600)
            if "put" in argv:
                return CommandResult(0, b"", b"", False, False)
            body = self.exec_replies.pop(0) if self.exec_replies else reply()
            return CommandResult(0, body, b"", False, False)
        return CommandResult(0, b"", b"", False, False)

    def verbs(self) -> list[str]:
        return [call[1] for call in self.calls]


async def test_a_session_creates_uploads_runs_and_always_removes_the_container() -> None:
    fake = FakeDocker(exec_replies=[reply(out=b"42\n")])
    sandbox = DockerSandbox(CONFIG, runner=fake)
    async with sandbox.session(get_language("python"), "print(42)", memory_limit_mb=64) as session:
        result = await session.run("", LIMITS)
    assert (result.status, result.stdout, result.time_ms, result.memory_kb) == (RunStatus.EXITED, "42\n", 12, 5000)
    assert fake.verbs() == ["run", "exec", "exec", "rm"]
    assert fake.stdins[1] == b"print(42)"  # source travels over stdin: no file is ever mounted into the container
    name = flag_value(fake.calls[0], "--name")
    assert fake.calls[-1][-2:] == ["--force", name]


async def test_the_container_is_removed_when_the_body_raises() -> None:
    fake = FakeDocker()
    sandbox = DockerSandbox(CONFIG, runner=fake)
    with pytest.raises(RuntimeError, match="judging blew up"):
        async with sandbox.session(get_language("python"), "x", memory_limit_mb=64):
            raise RuntimeError("judging blew up")
    assert fake.verbs()[-1] == "rm"


async def test_a_container_that_fails_to_start_is_a_sandbox_error_and_is_still_cleaned_up() -> None:
    fake = FakeDocker(run_code=125)
    sandbox = DockerSandbox(CONFIG, runner=fake)
    with pytest.raises(SandboxError, match="could not start"):
        async with sandbox.session(get_language("python"), "x", memory_limit_mb=64):
            pytest.fail("must not be reached")
    assert fake.verbs() == ["run", "rm"]


async def test_the_container_is_removed_when_the_task_is_cancelled() -> None:
    fake = FakeDocker(hang_exec=True)
    sandbox = DockerSandbox(CONFIG, runner=fake)

    async def judge() -> None:
        async with sandbox.session(get_language("python"), "x", memory_limit_mb=64):
            pytest.fail("the upload hangs, so this is never reached")

    task = asyncio.create_task(judge())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.05)
    assert fake.verbs()[-1] == "rm"


async def test_oversized_source_never_reaches_docker() -> None:
    fake = FakeDocker()
    sandbox = DockerSandbox(DockerSandboxConfig(max_source_bytes=10), runner=fake)
    with pytest.raises(SandboxError, match="size limit"):
        async with sandbox.session(get_language("python"), "x" * 11, memory_limit_mb=64):
            pytest.fail("must not be reached")
    assert "exec" not in fake.verbs()


async def test_compile_reports_the_compilers_own_diagnostics() -> None:
    failed = reply(out=b"", err=b"main.cpp:3: error: expected ';'", exit_code=1)
    fake = FakeDocker(exec_replies=[failed])
    sandbox = DockerSandbox(CONFIG, runner=fake)
    async with sandbox.session(get_language("cpp"), "int main(", memory_limit_mb=64) as session:
        compiled = await session.compile()
    assert compiled.ok is False
    assert "expected ';'" in compiled.output


async def test_interpreted_languages_skip_compilation() -> None:
    fake = FakeDocker()
    sandbox = DockerSandbox(CONFIG, runner=fake)
    async with sandbox.session(get_language("python"), "x", memory_limit_mb=64) as session:
        assert (await session.compile()).ok
    assert fake.verbs() == ["run", "exec", "rm"]  # only the source upload, no compile exec


async def test_docker_exec_failure_is_a_sandbox_error() -> None:
    class Failing(FakeDocker):
        async def __call__(self, argv, **kwargs) -> CommandResult:
            if argv[1] == "exec" and "run" in argv:
                return CommandResult(1, b"", b"Error response from daemon: container is not running", False, False)
            return await super().__call__(argv, **kwargs)

    sandbox = DockerSandbox(CONFIG, runner=Failing())
    async with sandbox.session(get_language("python"), "x", memory_limit_mb=64) as session:
        with pytest.raises(SandboxError, match="docker exec failed"):
            await session.run("", LIMITS)


async def test_reaper_removes_only_stale_sandbox_containers(monkeypatch) -> None:
    now = 1_000_000

    class Listing(FakeDocker):
        async def __call__(self, argv, **kwargs) -> CommandResult:
            if argv[1] == "ps":
                rows = f"sjx-old\t{now - 5000}\nsjx-new\t{now - 10}\nother-thing\t{now - 9999}\nsjx-bad\tnot-a-number\n"
                return CommandResult(0, rows.encode(), b"", False, False)
            return await super().__call__(argv, **kwargs)

    fake = Listing()
    sandbox = DockerSandbox(CONFIG, runner=fake)
    monkeypatch.setattr("sahujudge.docker_sandbox.time.time", lambda: now)
    removed = await sandbox.reap_stale(max_age_seconds=1000)
    assert removed == 1
    assert [call[-1] for call in fake.calls if call[1] == "rm"] == ["sjx-old"]
