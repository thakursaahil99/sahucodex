"""SahuJudge sandbox on Vercel Sandbox: one Firecracker microVM per submission, for hosts with no Docker daemon.

Isolation comes from the platform, and is applied when the microVM is created:

* a private microVM per session (its own kernel), destroyed in a `finally` however the session ends;
* `NetworkPolicy.deny_all()`: no route to the database, Redis, the internet or anything else;
* it starts from a prepared snapshot (Python, Node, g++ - see docs/judge.md), never from anything the user supplies;
* the sandbox holds no secrets: no environment variables are passed in, and the only file that goes in besides the
  submitted source is `supervisor.py`.

The in-VM supervisor is the same one the Docker sandbox uses and speaks the same protocol, so `VercelSession` only
replaces the transport (`docker exec` -> write stdin file, run, read stdout file) and inherits compile/run/limit
handling from `DockerSession`.
"""

from __future__ import annotations

import asyncio
import contextlib
import shlex
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sahujudge.docker_sandbox import DOCKER_TIMEOUT_S, DockerSession
from sahujudge.languages import WORKDIR, LanguageSpec
from sahujudge.process import CommandResult
from sahujudge.sandbox import SandboxError

SUPERVISOR_LOCAL = Path(__file__).with_name("supervisor.py")
SUPERVISOR_REMOTE = "/tmp/sjx/supervisor.py"  # noqa: S108 - inside the disposable microVM
IO_DIR = "/tmp/sjx"  # noqa: S108
SDK_CWD = "/vercel/sandbox"


@dataclass(frozen=True)
class VercelSandboxConfig:
    snapshot_id: str
    max_source_bytes: int = 65_536
    compile_output_bytes: int = 8_192
    vcpus: int = 1
    lifetime_s: int = 300  # the platform kills the microVM after this, even if we never get to destroy it


def container_memory_mb(language: LanguageSpec, limit_mb: int) -> int:
    return max(limit_mb + 64, language.min_container_memory_mb)


class VercelSession(DockerSession):
    """A `DockerSession` whose supervisor calls go to a Vercel microVM instead of `docker exec`."""

    def __init__(self, sandbox: VercelSandbox, box: Any, language: LanguageSpec, memory_mb: int) -> None:
        super().__init__(sandbox, box.name, language, memory_mb)  # type: ignore[arg-type]
        self._box = box

    async def _supervisor(
        self, args: Sequence[str], *, stdin: bytes = b"", timeout_s: float, max_output: int
    ) -> CommandResult:
        tag = uuid.uuid4().hex[:12]
        stdin_path, stdout_path = f"{IO_DIR}/in-{tag}", f"{IO_DIR}/out-{tag}"
        command = " ".join(["python3", SUPERVISOR_REMOTE, *(shlex.quote(a) for a in args)])
        try:
            await self._box.fs.write_bytes(stdin_path, stdin, cwd="/")
            done = await self._box.run_process(
                "sh",
                ["-c", f"{command} < {stdin_path} > {stdout_path}"],
                cwd="/",
                kill_after=timeout_s,
                capture_output=True,
            )
            if done.returncode != 0:
                detail = (done.stderr or "").strip()[:300]
                raise SandboxError(f"supervisor failed in the microVM ({done.returncode}): {detail}")
            stdout = await self._box.fs.read_bytes(stdout_path, cwd="/")
        except SandboxError:
            raise
        except Exception as exc:  # the SDK raises its own family of transport/API errors
            raise SandboxError(f"Vercel Sandbox call failed: {type(exc).__name__}: {str(exc)[:200]}") from exc
        if len(stdout) > max_output:
            raise SandboxError("sandbox supervisor did not finish within its limits")
        return CommandResult(returncode=0, stdout=stdout, stderr=b"", timed_out=False, truncated=False)


class VercelSandbox:
    def __init__(self, config: VercelSandboxConfig) -> None:
        self.config = config

    @asynccontextmanager
    async def session(
        self, language: LanguageSpec, source: str, *, memory_limit_mb: int
    ) -> AsyncIterator[VercelSession]:
        from vercel.sandbox import NetworkPolicy, SandboxResources, SnapshotSource, create_sandbox

        box = None
        try:
            try:
                box = await create_sandbox(
                    source=SnapshotSource(snapshot_id=self.config.snapshot_id),
                    network_policy=NetworkPolicy.deny_all(),
                    resources=SandboxResources(vcpus=self.config.vcpus),
                    execution_time_limit=self.config.lifetime_s,
                    tags={"app": "sahujudge"},
                )
                # /work is where LanguageSpec puts sources and binaries; the snapshot's user owns it for this VM only.
                # The SDK's filesystem calls run in the platform's default cwd, which a snapshot does not contain.
                prepared = await box.run_process(
                    "sh",
                    [
                        "-c",
                        f"mkdir -p {SDK_CWD} {IO_DIR} && sudo -n mkdir -p {WORKDIR} && "
                        f"sudo -n chown $(id -u):$(id -g) {WORKDIR}",
                    ],
                    cwd="/",
                    kill_after=DOCKER_TIMEOUT_S,
                    capture_output=True,
                )
                if prepared.returncode != 0:
                    raise SandboxError(f"could not prepare the microVM: {(prepared.stderr or '').strip()[:200]}")
                await box.fs.write_bytes(SUPERVISOR_REMOTE, SUPERVISOR_LOCAL.read_bytes(), cwd="/")
            except SandboxError:
                raise
            except Exception as exc:
                raise SandboxError(f"could not start the microVM: {type(exc).__name__}: {str(exc)[:200]}") from exc
            memory_mb = container_memory_mb(language, memory_limit_mb)
            session = VercelSession(self, box, language, memory_mb)
            await session.put_source(source.encode("utf-8"))
            yield session
        finally:
            if box is not None:
                # Shielded so a cancelled request still destroys its microVM; the lifetime limit is the backstop.
                with contextlib.suppress(Exception):
                    await asyncio.shield(box.destroy())
