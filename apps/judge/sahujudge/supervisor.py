"""Runs *inside* the sandbox container, as the unprivileged sandbox user. Standard library only.

It is copied into the runner image at /opt/sjx/supervisor.py and driven by the judge worker through `docker exec`:

    supervisor.py put --path /work/main.py --max-bytes N        stdin -> file (created exclusively, mode 0600)
    supervisor.py run --time-ms .. --wall-ms .. --memory-mb .. -- CMD ARG...
    supervisor.py idle --seconds N                              the container's main process (self-destructs after N)

`run` starts CMD in its own session with resource limits, feeds it this process's stdin, and measures it. It enforces:
CPU time (polled, plus RLIMIT_CPU as a backstop), wall-clock time, resident memory (polled; the container's cgroup limit
is the hard backstop), output size (the child's stdout goes to a pipe that is read with a cap, so it never touches
disk), file size, open files and core dumps. When the child is done, however it ended, it kills **every** process the
sandbox user owns, so nothing survives into the next test. It then prints one JSON header line followed by the raw
stdout and stderr bytes. The header is written by this process before any of the child's bytes, and the judge reads
only the first line as the header, so a program cannot forge it by printing one.

The worker never trusts this program for *correctness*: the verdict comes from comparing the captured stdout with the
expected output on the worker side. A program that tampers with this supervisor can at worst misreport its own runtime
or memory, or make the judge fail with SYSTEM_ERROR; it cannot obtain ACCEPTED, and it cannot see anything it was not
already given. Linux only (it reads /proc and the cgroup).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import posixpath
import selectors
import subprocess
import sys
import time

# Overridable only so the behaviour tests can run on a host without /work; the sandbox's environment is set by the
# worker (`docker run --env`), never by submitted code.
WORKDIR = os.environ.get("SJX_WORKDIR", "/work")
POLL_SECONDS = 0.01
DRAIN_SECONDS = 0.25
MAX_PUT_DEPTH_BELOW_WORKDIR = 1  # main.py, or dir/main.py
DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"
# Linux signal numbers, spelled out so `classify` can be unit-tested on hosts whose `signal` module lacks them.
SIGKILL, SIGXCPU, SIGXFSZ = 9, 24, 25


# --- pure helpers (unit-tested on any OS) -----------------------------------------------------------------------------


def parse_stat_cpu_ms(text: str, clock_ticks: int) -> int | None:
    """CPU milliseconds (utime + stime) from the text of /proc/<pid>/stat. The command name is in parentheses and may
    contain spaces or parentheses, so fields are counted from the LAST ')'."""
    try:
        fields = text[text.rindex(")") + 2 :].split()
        return int((int(fields[11]) + int(fields[12])) * 1000 / clock_ticks)
    except (ValueError, IndexError):
        return None


def parse_status_rss_kb(text: str) -> int | None:
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            with contextlib.suppress(ValueError, IndexError):
                return int(line.split()[1])
    return None


def parse_oom_kills(text: str) -> int | None:
    for line in text.splitlines():
        if line.startswith("oom_kill "):
            with contextlib.suppress(ValueError, IndexError):
                return int(line.split()[1])
    return None


def classify(
    *, killed: str | None, code: int, cpu_ms: int, memory_kb: int, time_ms: int, memory_limit_kb: int, oom: bool
) -> tuple[str, int | None, int | None]:
    """(status, exit_code, signal) for a finished child; `code` is os.waitstatus_to_exitcode (negative = signal)."""
    exit_code = code if code >= 0 else None
    sig = -code if code < 0 else None
    if killed is not None:
        return killed, exit_code, sig
    if oom and sig == SIGKILL:
        return "MEMORY", exit_code, sig
    if sig is not None:
        if sig == SIGXCPU or cpu_ms > time_ms:
            return "TIMEOUT", exit_code, sig
        if sig == SIGXFSZ:
            return "OUTPUT_LIMIT", exit_code, sig
        return "SIGNALED", exit_code, sig
    if cpu_ms > time_ms:
        return "TIMEOUT", exit_code, sig
    if memory_kb > memory_limit_kb:
        return "MEMORY", exit_code, sig
    return "EXITED", exit_code, sig


def safe_work_path(path: str) -> str:
    """Only files directly under /work (or one directory below) may be written by `put`."""
    normal = posixpath.normpath(path)
    if not normal.startswith(WORKDIR + "/") or normal[len(WORKDIR) + 1 :].count("/") > MAX_PUT_DEPTH_BELOW_WORKDIR:
        raise ValueError("path must be inside the work directory")
    return normal


def build_header(
    *,
    status: str,
    exit_code: int | None,
    sig: int | None,
    cpu_ms: int,
    wall_ms: int,
    memory_kb: int,
    out: int,
    err: int,
) -> str:
    return json.dumps(
        {
            "status": status,
            "exit_code": exit_code,
            "signal": sig,
            "cpu_ms": cpu_ms,
            "wall_ms": wall_ms,
            "memory_kb": memory_kb,
            "stdout_len": out,
            "stderr_len": err,
        },
        separators=(",", ":"),
    )


# --- commands (Linux) -------------------------------------------------------------------------------------------------


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="ascii", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _oom_kills() -> int | None:
    text = _read("/sys/fs/cgroup/memory.events")
    return parse_oom_kills(text) if text is not None else None


def _kill_leftovers(child_pgid: int) -> None:
    """Kills whatever the child left behind.

    Inside the sandbox (the runner image sets SJX_SANDBOX=1) that is EVERY process this user owns: kill(-1) signals
    every process the caller may signal except PID 1 and the caller itself. The container's main process runs as a
    different user, so it survives, and so does this supervisor. Anywhere else (a developer running the tests on their
    own machine) kill(-1) would take out the caller's whole session, so only the child's process group is killed."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        if os.environ.get("SJX_SANDBOX") == "1":
            os.kill(-1, SIGKILL)
        else:
            os.killpg(child_pgid, SIGKILL)


def cmd_put(args: argparse.Namespace) -> int:
    path = safe_work_path(args.path)
    data = sys.stdin.buffer.read(args.max_bytes + 1)
    if len(data) > args.max_bytes:
        print("file too large", file=sys.stderr)
        return 2
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    return 0


def cmd_idle(args: argparse.Namespace) -> int:
    time.sleep(args.seconds)
    return 0


def cmd_run(args: argparse.Namespace, command: list[str]) -> int:
    import resource  # POSIX only, so imported here to keep the module importable elsewhere

    clock_ticks = os.sysconf("SC_CLK_TCK")
    memory_limit_kb = args.memory_mb * 1024
    cpu_seconds = -(-args.time_ms // 1000) + 1  # RLIMIT_CPU is whole seconds: a backstop behind the precise poll
    stack_bytes = args.stack_mb * 1024 * 1024

    def apply_limits() -> None:  # runs in the child between fork and exec
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        resource.setrlimit(resource.RLIMIT_STACK, (stack_bytes, stack_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (args.fsize_bytes, args.fsize_bytes))
        resource.setrlimit(resource.RLIMIT_NOFILE, (args.nofile, args.nofile))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    env = {"PATH": DEFAULT_PATH, "HOME": WORKDIR, "LANG": "C.UTF-8", "TMPDIR": "/tmp"}  # noqa: S108
    for item in args.env:
        key, _, value = item.partition("=")
        env[key] = value

    oom_before = _oom_kills()
    start = time.monotonic()
    proc = subprocess.Popen(  # noqa: S603  (fixed argv from the judge's language table; never a shell)
        command,
        stdin=sys.stdin.fileno(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=WORKDIR,
        env=env,
        start_new_session=True,
        preexec_fn=apply_limits,
    )
    pid = proc.pid
    assert proc.stdout is not None
    assert proc.stderr is not None
    selector = selectors.DefaultSelector()
    for stream in (proc.stdout, proc.stderr):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ)

    out = bytearray()
    err = bytearray()
    out_over = False
    peak_rss_kb = 0
    killed: str | None = None

    def pump(timeout: float) -> None:
        nonlocal out_over
        for key, _ in selector.select(timeout=timeout):
            try:
                data = os.read(key.fd, 65536)
            except BlockingIOError:
                continue
            if not data:
                selector.unregister(key.fileobj)
                continue
            if key.fileobj is proc.stdout:
                room = args.max_output - len(out)
                out.extend(data[: max(room, 0)])
                out_over = out_over or len(data) > room
            else:  # stderr: keep the head, silently drop the rest (the child must not block on a full pipe)
                room = args.max_stderr - len(err)
                err.extend(data[: max(room, 0)])

    while True:
        pump(POLL_SECONDS)
        done, wait_status, usage = os.wait4(pid, os.WNOHANG)
        if done:
            break
        if killed is not None:
            continue
        cpu_ms = parse_stat_cpu_ms(_read(f"/proc/{pid}/stat") or "", clock_ticks)
        rss_kb = parse_status_rss_kb(_read(f"/proc/{pid}/status") or "")
        peak_rss_kb = max(peak_rss_kb, rss_kb or 0)
        if out_over:
            killed = "OUTPUT_LIMIT"
        elif (cpu_ms is not None and cpu_ms > args.time_ms) or (time.monotonic() - start) * 1000 > args.wall_ms:
            killed = "TIMEOUT"
        elif rss_kb is not None and rss_kb > memory_limit_kb:
            killed = "MEMORY"
        if killed is not None:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(pid, SIGKILL)
    proc.returncode = 0  # already reaped by wait4; stops Popen from waiting again

    wall_ms = int((time.monotonic() - start) * 1000)
    _kill_leftovers(pid)
    deadline = time.monotonic() + DRAIN_SECONDS
    while selector.get_map() and time.monotonic() < deadline:
        pump(POLL_SECONDS)

    cpu_ms = int((usage.ru_utime + usage.ru_stime) * 1000)
    memory_kb = max(int(usage.ru_maxrss), peak_rss_kb)
    oom_after = _oom_kills()
    if out_over and killed is None:
        killed = "OUTPUT_LIMIT"
    status, exit_code, sig = classify(
        killed=killed,
        code=os.waitstatus_to_exitcode(wait_status),
        cpu_ms=cpu_ms,
        memory_kb=memory_kb,
        time_ms=args.time_ms,
        memory_limit_kb=memory_limit_kb,
        oom=oom_before is not None and oom_after is not None and oom_after > oom_before,
    )
    header = build_header(
        status=status,
        exit_code=exit_code,
        sig=sig,
        cpu_ms=cpu_ms,
        wall_ms=wall_ms,
        memory_kb=memory_kb,
        out=len(out),
        err=len(err),
    )
    stdout = sys.stdout.buffer
    stdout.write(header.encode("ascii") + b"\n" + bytes(out) + bytes(err))
    stdout.flush()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="supervisor")
    sub = parser.add_subparsers(dest="command", required=True)

    put = sub.add_parser("put")
    put.add_argument("--path", required=True)
    put.add_argument("--max-bytes", type=int, required=True)

    idle = sub.add_parser("idle")
    idle.add_argument("--seconds", type=int, required=True)

    run = sub.add_parser("run")
    run.add_argument("--time-ms", type=int, required=True)
    run.add_argument("--wall-ms", type=int, required=True)
    run.add_argument("--memory-mb", type=int, required=True)
    run.add_argument("--stack-mb", type=int, default=64)
    run.add_argument("--max-output", type=int, default=1_048_576)
    run.add_argument("--max-stderr", type=int, default=8192)
    run.add_argument("--fsize-bytes", type=int, default=1_048_576)
    run.add_argument("--nofile", type=int, default=128)
    run.add_argument("--env", action="append", default=[])
    return parser


def main(argv: list[str]) -> int:
    command: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, command = argv[:split], argv[split + 1 :]
    args = build_parser().parse_args(argv)
    if args.command == "put":
        return cmd_put(args)
    if args.command == "idle":
        return cmd_idle(args)
    if not command:
        print("run needs a command after --", file=sys.stderr)
        return 2
    return cmd_run(args, command)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
