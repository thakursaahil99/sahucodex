"""The in-container supervisor.

The parsing and classification helpers are tested everywhere. The behaviour tests run the real supervisor as a
subprocess and need Linux (`/proc`, `wait4`, rlimits); they run in CI on Linux and are skipped on Windows. They run
natively, so the fork-bomb and network probes live in the Docker integration tests instead, where a container's limits
contain them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sahujudge import supervisor
from sahujudge.docker_sandbox import parse_supervisor_output

SUPERVISOR = Path(supervisor.__file__)

# --- pure helpers -------------------------------------------------------------------------------------------------------


def test_cpu_time_is_read_from_after_the_last_parenthesis() -> None:
    # utime=250 and stime=50 ticks at 100 Hz -> 3000 ms, even though the command name contains spaces and ')'.
    stat = "42 (evil ) name) R " + " ".join(["0"] * 10) + " 250 50 0 0"
    assert supervisor.parse_stat_cpu_ms(stat, 100) == 3000
    assert supervisor.parse_stat_cpu_ms("garbage", 100) is None
    assert supervisor.parse_stat_cpu_ms("1 (x) R 1", 100) is None


def test_rss_and_oom_parsers() -> None:
    assert supervisor.parse_status_rss_kb("Name:\tpython\nVmRSS:\t  12345 kB\nThreads:\t1\n") == 12345
    assert supervisor.parse_status_rss_kb("Name:\tx\n") is None
    assert supervisor.parse_oom_kills("low 0\nhigh 0\noom 1\noom_kill 3\n") == 3
    assert supervisor.parse_oom_kills("nothing here") is None


BASE = {"killed": None, "cpu_ms": 10, "memory_kb": 1000, "time_ms": 1000, "memory_limit_kb": 64_000, "oom": False}


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"code": 0}, ("EXITED", 0, None)),
        ({"code": 3}, ("EXITED", 3, None)),
        ({"code": -11}, ("SIGNALED", None, 11)),
        ({"code": -supervisor.SIGXCPU}, ("TIMEOUT", None, supervisor.SIGXCPU)),
        ({"code": -supervisor.SIGKILL, "cpu_ms": 2000}, ("TIMEOUT", None, supervisor.SIGKILL)),  # RLIMIT_CPU backstop
        ({"code": -supervisor.SIGKILL, "oom": True}, ("MEMORY", None, supervisor.SIGKILL)),  # kernel OOM killer
        ({"code": -supervisor.SIGKILL}, ("SIGNALED", None, supervisor.SIGKILL)),
        ({"code": -supervisor.SIGXFSZ}, ("OUTPUT_LIMIT", None, supervisor.SIGXFSZ)),
        ({"code": 0, "cpu_ms": 1001}, ("TIMEOUT", 0, None)),  # finished, but over the CPU limit
        ({"code": 0, "memory_kb": 64_001}, ("MEMORY", 0, None)),  # finished, but its peak was over the limit
        ({"code": 0, "killed": "OUTPUT_LIMIT"}, ("OUTPUT_LIMIT", 0, None)),
    ],
)
def test_classify(overrides, expected) -> None:
    assert supervisor.classify(**{**BASE, **overrides}) == expected


@pytest.mark.parametrize(
    "path", ["/etc/passwd", "/work/../etc/passwd", "/workshop/x", "work/x", "/work", "/work/a/b/c/d"]
)
def test_put_refuses_paths_outside_work(path) -> None:
    with pytest.raises(ValueError):
        supervisor.safe_work_path(path)


def test_put_accepts_the_source_paths() -> None:
    assert supervisor.safe_work_path("/work/main.py") == "/work/main.py"


def test_header_is_a_single_ascii_json_line() -> None:
    header = supervisor.build_header(
        status="EXITED", exit_code=0, sig=None, cpu_ms=1, wall_ms=2, memory_kb=3, out=4, err=5
    )
    assert "\n" not in header
    assert json.loads(header)["stdout_len"] == 4
    header.encode("ascii")


# --- behaviour (Linux) --------------------------------------------------------------------------------------------------

linux = pytest.mark.linux


def run_supervisor(tmp_path: Path, code: str, *, stdin: bytes = b"", **limits: int) -> tuple[dict, bytes, bytes, float]:
    import time

    opts = {"time_ms": 2000, "wall_ms": 5000, "memory_mb": 512, "max_output": 100_000, "max_stderr": 1000} | limits
    argv = [sys.executable, str(SUPERVISOR), "run"]
    for key, value in opts.items():
        argv += [f"--{key.replace('_', '-')}", str(value)]
    argv += ["--", sys.executable, "-c", code]
    env = {**os.environ, "SJX_WORKDIR": str(tmp_path)}
    env.pop("SJX_SANDBOX", None)  # kill(-1) must never be enabled on a developer or CI machine
    started = time.monotonic()
    done = subprocess.run(argv, input=stdin, capture_output=True, env=env, timeout=60, check=False)
    elapsed = time.monotonic() - started
    assert done.returncode == 0, done.stderr.decode()
    header, out, err = parse_supervisor_output(done.stdout)
    return dict(header), out, err, elapsed


@linux
def test_normal_run_reports_output_and_measurements(tmp_path) -> None:
    header, out, _, _ = run_supervisor(tmp_path, "print('hello')")
    assert (header["status"], header["exit_code"], out) == ("EXITED", 0, b"hello\n")
    assert header["memory_kb"] > 0
    assert header["cpu_ms"] >= 0


@linux
def test_exit_code_stderr_and_stdin_passthrough(tmp_path) -> None:
    code = "import sys; sys.stderr.write('bad'); print(sys.stdin.read().upper()); sys.exit(3)"
    header, out, err, _ = run_supervisor(tmp_path, code, stdin=b"abc")
    assert (header["status"], header["exit_code"], out, err) == ("EXITED", 3, b"ABC\n", b"bad")


@linux
def test_infinite_loop_is_a_timeout_and_is_stopped_promptly(tmp_path) -> None:
    header, _, _, elapsed = run_supervisor(tmp_path, "while True: pass", time_ms=300)
    assert header["status"] == "TIMEOUT"
    assert elapsed < 4


@linux
def test_sleeping_forever_hits_the_wall_clock_limit(tmp_path) -> None:
    header, _, _, elapsed = run_supervisor(tmp_path, "import time; time.sleep(60)", wall_ms=400)
    assert header["status"] == "TIMEOUT"
    assert elapsed < 4


@linux
def test_output_flood_is_capped_and_stopped(tmp_path) -> None:
    flood = "import sys\nwhile True:\n    sys.stdout.write('x' * 65536)\n    sys.stdout.flush()"
    header, out, _, elapsed = run_supervisor(tmp_path, flood, max_output=10_000)
    assert header["status"] == "OUTPUT_LIMIT"
    assert len(out) <= 10_000
    assert elapsed < 10


@linux
def test_stderr_flood_is_truncated_without_blocking_the_program(tmp_path) -> None:
    code = "import sys\nfor _ in range(2000): sys.stderr.write('e' * 1000)\nprint('done')"
    header, out, err, _ = run_supervisor(tmp_path, code, max_stderr=500)
    assert (header["status"], out) == ("EXITED", b"done\n")
    assert len(err) == 500


@linux
def test_a_crash_by_signal_is_reported_with_the_signal(tmp_path) -> None:
    header, _, _, _ = run_supervisor(tmp_path, "import os, signal; os.kill(os.getpid(), 11)")
    assert (header["status"], header["signal"]) == ("SIGNALED", 11)


@linux
def test_memory_over_the_limit_is_detected(tmp_path) -> None:
    header, _, _, elapsed = run_supervisor(
        tmp_path, "import time\nblob = 'x' * (400 * 1024 * 1024)\ntime.sleep(20)", memory_mb=100
    )
    assert header["status"] == "MEMORY"
    assert elapsed < 10


@linux
def test_a_program_cannot_forge_the_header_by_printing_one(tmp_path) -> None:
    fake = json.dumps({"status": "EXITED", "exit_code": 0, "cpu_ms": 0, "wall_ms": 0, "memory_kb": 0})
    header, out, _, _ = run_supervisor(tmp_path, f"print({fake!r})\nimport sys; sys.exit(7)")
    assert (header["status"], header["exit_code"]) == ("EXITED", 7)
    assert out.decode().startswith('{"status"')


def _alive(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return state != "Z"


@linux
def test_processes_left_behind_are_killed(tmp_path) -> None:
    code = (
        "import subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print(child.pid)"
    )
    header, out, _, _ = run_supervisor(tmp_path, code)
    assert header["status"] == "EXITED"
    pid = int(out.strip())
    import time

    for _ in range(50):
        if not _alive(pid):
            break
        time.sleep(0.05)
    assert not _alive(pid), "a background process outlived the run"


@linux
def test_put_writes_exclusively_with_private_permissions(tmp_path) -> None:
    env = {**os.environ, "SJX_WORKDIR": str(tmp_path)}
    target = tmp_path / "main.py"

    def put(data: bytes, max_bytes: int = 100) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, str(SUPERVISOR), "put", "--path", str(target), "--max-bytes", str(max_bytes)],
            input=data,
            capture_output=True,
            env=env,
            check=False,
        )

    # SJX_WORKDIR is not /work here, so point the module's guard at tmp_path via the environment (same mechanism).
    assert put(b"print(1)").returncode == 0
    assert target.read_bytes() == b"print(1)"
    assert (target.stat().st_mode & 0o777) == 0o600
    assert put(b"overwrite").returncode != 0  # O_EXCL: a second upload cannot replace the first
    assert target.read_bytes() == b"print(1)"
    other = tmp_path / "big.py"
    target = other
    assert put(b"x" * 101).returncode == 2
    assert not other.exists()
