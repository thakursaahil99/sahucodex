"""The production sandbox: one hardened container per submission, driven through the `docker` CLI.

Isolation, all applied when the container is created (see `build_run_argv`, which is asserted in tests):

* `--network none`: no network stack at all, so no route to PostgreSQL, Redis, the internet or other containers.
* `--read-only` root filesystem; the only writable places are two small `tmpfs` mounts (`/work`, `/tmp`) that vanish
  with the container. **No bind mounts, no volumes, no host paths** are ever passed.
* `--cap-drop ALL`, `no-new-privileges`, Docker's default seccomp profile, never `--privileged`, never a device.
* Non-root: the container's main process runs as one unprivileged user and user code as another, so user code cannot
  signal, ptrace or read the memory of the container's init process.
* Limits: memory (with swap disabled), CPU, PIDs (fork bombs), open files, core dumps; per-run CPU, wall-clock, output
  and stack limits are enforced by the in-container supervisor.
* The container removes itself: `--rm`, a hard self-destruct timer on its main process, an explicit `docker rm -f` in
  a `finally`, and a janitor (`reap_stale`) for anything a killed worker left behind.

The worker talks to a DEDICATED Docker daemon (`DOCKER_HOST`), never the host's socket, and no container that runs user
code has access to any daemon. See docs/judge.md.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sahujudge.languages import WORKDIR, LanguageSpec
from sahujudge.process import CommandResult, run_command
from sahujudge.sandbox import CompileResult, RunLimits, RunResult, RunStatus, SandboxError

SUPERVISOR = "/opt/sjx/supervisor.py"
LABEL = "sahucodex.judge"
LABEL_CREATED = "sahucodex.judge.created"
DOCKER_TIMEOUT_S = 30.0
COMPILE_FSIZE_BYTES = 64 * 1024 * 1024
EXEC_SLACK_S = 5.0

CommandRunner = Callable[..., Awaitable[CommandResult]]


@dataclass(frozen=True)
class DockerSandboxConfig:
    image: str = "sahucodex/runner:1"
    docker_bin: str = "docker"
    docker_host: str | None = None
    runtime: str | None = None  # e.g. "runsc" (gVisor)
    pids_limit: int = 64
    cpus: float = 1.0
    tmpfs_mb: int = 64
    memory_slack_mb: int = 128  # room above the problem's limit for the tmpfs and the supervisor
    ttl_seconds: int = 600  # the container's main process exits, and so removes the container, after this long
    max_source_bytes: int = 65_536
    compile_output_bytes: int = 8_192
    user_uid: int = 10001  # user code, and the owner of /work
    init_uid: int = 10002  # the container's main process


def container_memory_mb(config: DockerSandboxConfig, language: LanguageSpec, memory_limit_mb: int) -> int:
    return max(memory_limit_mb + config.memory_slack_mb, language.min_container_memory_mb)


def build_run_argv(config: DockerSandboxConfig, name: str, memory_mb: int, *, created_at: int) -> list[str]:
    """`docker run` for the sandbox container. There is deliberately no way to add a mount, port, device, capability,
    network or privileged flag through this function."""
    argv = [
        config.docker_bin,
        "run",
        "--detach",
        "--rm",
        "--name",
        name,
        "--label",
        f"{LABEL}=1",
        "--label",
        f"{LABEL_CREATED}={created_at}",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        str(config.pids_limit),
        "--memory",
        f"{memory_mb}m",
        "--memory-swap",
        f"{memory_mb}m",
        "--cpus",
        str(config.cpus),
        "--ulimit",
        "nofile=256:256",
        "--ulimit",
        "core=0:0",
        "--user",
        f"{config.init_uid}:{config.init_uid}",
        "--tmpfs",
        f"{WORKDIR}:rw,exec,nosuid,nodev,size={config.tmpfs_mb}m,uid={config.user_uid},gid={config.user_uid},mode=0700",
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,nodev,size=32m,uid={config.user_uid},gid={config.user_uid},mode=1777",  # noqa: S108
        "--workdir",
        WORKDIR,
        "--hostname",
        "sandbox",
        "--env",
        "SJX_SANDBOX=1",
        "--init",
        "--log-driver",
        "none",
        "--stop-timeout",
        "1",
    ]
    if config.runtime:
        argv += ["--runtime", config.runtime]
    argv += [config.image, "python3", SUPERVISOR, "idle", "--seconds", str(config.ttl_seconds)]
    return argv


def build_exec_argv(config: DockerSandboxConfig, name: str, supervisor_args: Sequence[str]) -> list[str]:
    return [
        config.docker_bin,
        "exec",
        "--interactive",
        "--user",
        f"{config.user_uid}:{config.user_uid}",
        "--workdir",
        WORKDIR,
        name,
        "python3",
        SUPERVISOR,
        *supervisor_args,
    ]


def docker_env(config: DockerSandboxConfig) -> dict[str, str]:
    """The CLI gets a minimal environment: it must not inherit the worker's secrets (database URL, Redis password)."""
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if key in os.environ}
    env["DOCKER_CONFIG"] = os.path.join(tempfile.gettempdir(), ".sahujudge-docker")
    if config.docker_host:
        env["DOCKER_HOST"] = config.docker_host
    return env


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n… (output truncated)"


def parse_supervisor_output(raw: bytes) -> tuple[Mapping[str, Any], bytes, bytes]:
    """Splits the supervisor's reply into (header, stdout, stderr). Anything malformed is a SandboxError."""
    header_line, newline, body = raw.partition(b"\n")
    if not newline:
        raise SandboxError("sandbox supervisor returned no header")
    try:
        header = json.loads(header_line)
        out_len, err_len = header["stdout_len"], header["stderr_len"]
        if (
            not isinstance(header, dict)
            or not all(isinstance(header[key], int) for key in ("cpu_ms", "wall_ms", "memory_kb"))
            or not isinstance(out_len, int)
            or not isinstance(err_len, int)
            or out_len < 0
            or err_len < 0
            or out_len + err_len != len(body)
            or header["status"] not in RunStatus.__members__
        ):
            raise ValueError("inconsistent header")
    except (ValueError, KeyError, TypeError) as exc:
        raise SandboxError("sandbox supervisor returned a malformed reply") from exc
    return header, body[:out_len], body[out_len:]


class DockerSession:
    def __init__(self, sandbox: DockerSandbox, name: str, language: LanguageSpec, container_memory: int) -> None:
        self._sandbox = sandbox
        self._name = name
        self._language = language
        self._container_memory = container_memory

    async def _supervisor(
        self, args: Sequence[str], *, stdin: bytes = b"", timeout_s: float, max_output: int
    ) -> CommandResult:
        argv = build_exec_argv(self._sandbox.config, self._name, args)
        result = await self._sandbox.command(argv, stdin=stdin, timeout_s=timeout_s, max_output=max_output)
        if result.timed_out or result.truncated:
            raise SandboxError("sandbox supervisor did not finish within its limits")
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()[:300]
            raise SandboxError(f"docker exec failed ({result.returncode}): {detail}")
        return result

    async def put_source(self, source: bytes) -> None:
        max_bytes = self._sandbox.config.max_source_bytes
        if len(source) > max_bytes:
            raise SandboxError("source exceeds the sandbox size limit")
        await self._supervisor(
            ["put", "--path", self._language.source_path, "--max-bytes", str(max_bytes)],
            stdin=source,
            timeout_s=DOCKER_TIMEOUT_S,
            max_output=4096,
        )

    async def _run(self, command: Sequence[str], *, stdin: bytes, limits: RunLimits, fsize_bytes: int) -> RunResult:
        args = [
            "run",
            "--time-ms",
            str(limits.time_ms),
            "--wall-ms",
            str(limits.wall_ms),
            "--memory-mb",
            str(limits.memory_mb),
            "--stack-mb",
            str(limits.stack_mb),
            "--max-output",
            str(limits.max_output_bytes),
            "--max-stderr",
            str(limits.max_stderr_bytes),
            "--fsize-bytes",
            str(fsize_bytes),
            "--nofile",
            str(limits.nofile),
        ]
        for key, value in self._language.env:
            args += ["--env", f"{key}={value}"]
        args += ["--", *command]
        cap = limits.max_output_bytes + limits.max_stderr_bytes + 4096
        result = await self._supervisor(
            args, stdin=stdin, timeout_s=limits.wall_ms / 1000 + EXEC_SLACK_S, max_output=cap
        )
        header, out, err = parse_supervisor_output(result.stdout)
        return RunResult(
            status=RunStatus(header["status"]),
            exit_code=header["exit_code"] if isinstance(header["exit_code"], int) else None,
            signal=header["signal"] if isinstance(header["signal"], int) else None,
            time_ms=header["cpu_ms"],
            wall_ms=header["wall_ms"],
            memory_kb=header["memory_kb"],
            stdout=out.decode("utf-8", "replace"),
            stderr=err.decode("utf-8", "replace"),
        )

    async def compile(self) -> CompileResult:
        command = self._language.compile
        if command is None:
            return CompileResult(ok=True, output="")
        config = self._sandbox.config
        limits = RunLimits(
            time_ms=self._language.compile_time_ms,
            wall_ms=self._language.compile_time_ms * 2,
            memory_mb=self._container_memory,
            max_output_bytes=config.compile_output_bytes * 4,
            max_stderr_bytes=config.compile_output_bytes * 4,
            nofile=self._language.compile_nofile_limit,
        )
        result = await self._run(command, stdin=b"", limits=limits, fsize_bytes=COMPILE_FSIZE_BYTES)
        if result.status is RunStatus.EXITED and result.exit_code == 0:
            return CompileResult(ok=True, output="")
        if result.status is RunStatus.TIMEOUT:
            return CompileResult(ok=False, output="Compilation timed out.")
        if result.status is RunStatus.MEMORY:
            return CompileResult(ok=False, output="The compiler ran out of memory.")
        text = (result.stderr or result.stdout).strip() or "Compilation failed."
        return CompileResult(ok=False, output=_clip(text, config.compile_output_bytes))

    async def run(self, stdin: str, limits: RunLimits) -> RunResult:
        fsize_bytes = self._language.run_fsize_bytes or limits.max_output_bytes
        return await self._run(self._language.run, stdin=stdin.encode("utf-8"), limits=limits, fsize_bytes=fsize_bytes)


class DockerSandbox:
    def __init__(self, config: DockerSandboxConfig, *, runner: CommandRunner = run_command) -> None:
        self.config = config
        self._runner = runner

    async def command(
        self, argv: Sequence[str], *, stdin: bytes | None = None, timeout_s: float, max_output: int
    ) -> CommandResult:
        return await self._runner(
            argv, stdin=stdin, timeout_s=timeout_s, max_output_bytes=max_output, env=docker_env(self.config)
        )

    async def _docker(self, args: Sequence[str], *, timeout_s: float = DOCKER_TIMEOUT_S) -> CommandResult:
        return await self.command([self.config.docker_bin, *args], timeout_s=timeout_s, max_output=65_536)

    @asynccontextmanager
    async def session(
        self, language: LanguageSpec, source: str, *, memory_limit_mb: int
    ) -> AsyncIterator[DockerSession]:
        name = f"sjx-{uuid.uuid4().hex}"
        memory_mb = container_memory_mb(self.config, language, memory_limit_mb)
        try:
            argv = build_run_argv(self.config, name, memory_mb, created_at=int(time.time()))
            started = await self.command(argv, timeout_s=DOCKER_TIMEOUT_S, max_output=65_536)
            if started.returncode != 0 or started.timed_out:
                detail = started.stderr.decode("utf-8", "replace").strip()[:300]
                raise SandboxError(f"could not start the sandbox container: {detail or 'timed out'}")
            session = DockerSession(self, name, language, memory_mb)
            await session.put_source(source.encode("utf-8"))
            yield session
        finally:
            # Shielded so a cancelled task (worker shutdown, Celery time limit) still removes its container.
            await asyncio.shield(self._remove(name))

    async def _remove(self, name: str) -> None:
        # Best effort: `--rm` and the container's self-destruct timer are the backstops if this fails.
        with contextlib.suppress(Exception):
            await self._docker(["rm", "--force", name], timeout_s=DOCKER_TIMEOUT_S)

    async def reap_stale(self, max_age_seconds: int) -> int:
        """Removes sandbox containers older than `max_age_seconds` (leftovers of a killed worker). Returns the count."""
        listing = await self._docker(
            [
                "ps",
                "--all",
                "--filter",
                f"label={LABEL}=1",
                "--format",
                '{{.Names}}\t{{.Label "' + LABEL_CREATED + '"}}',
            ]
        )
        if listing.returncode != 0:
            raise SandboxError("could not list sandbox containers")
        cutoff = time.time() - max_age_seconds
        removed = 0
        for line in listing.stdout.decode("utf-8", "replace").splitlines():
            name, _, created = line.partition("\t")
            if name.startswith("sjx-") and created.strip().isdigit() and int(created) < cutoff:
                await self._remove(name)
                removed += 1
        return removed

    async def ensure_image(self, build_context: Path) -> bool:
        """Builds the runner image into the sandbox daemon if it is missing. Returns True if it had to build."""
        inspect = await self._docker(["image", "inspect", self.config.image])
        if inspect.returncode == 0:
            return False
        build = await self._docker(
            ["build", "--tag", self.config.image, "--file", str(build_context / "Dockerfile"), str(build_context)],
            timeout_s=1800,
        )
        if build.returncode != 0:
            raise SandboxError(f"building {self.config.image} failed: {build.stderr.decode('utf-8', 'replace')[-500:]}")
        return True
