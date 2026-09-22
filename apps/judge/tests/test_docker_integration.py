"""The mandatory sandbox security tests, against a REAL Docker daemon and the real runner image.

Skipped unless SJX_DOCKER_TESTS=1 and a `docker` CLI is on PATH (see docs/judge.md#testing). CI runs them on every push.
Point DOCKER_HOST / SJX_DOCKER_HOST at a throwaway daemon, never at one that runs anything you care about: these tests
deliberately run hostile programs (fork bombs, memory bombs, network and filesystem probes) inside sandboxes.

Every test asserts two things: the attempt FAILED SAFELY (the right verdict, or the probe reports "blocked"), and the
system stayed healthy (a normal submission still passes afterwards, and no sandbox container is left behind).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest
import pytest_asyncio

from sahujudge import supervisor
from sahujudge.checkers import LinesChecker
from sahujudge.docker_sandbox import LABEL, DockerSandbox, DockerSandboxConfig
from sahujudge.engine import JudgeConfig, JudgeReport, JudgeTest, Verdict, judge_tests
from sahujudge.languages import get_language
from sahujudge.sandbox import SandboxError

pytestmark = pytest.mark.docker

IMAGE = "sahucodex/runner:integration-test"
REPO = Path(__file__).resolve().parents[3]
HOST = os.environ.get("SJX_DOCKER_HOST")


def docker(*args: str, check: bool = True) -> str:
    env = {**os.environ, **({"DOCKER_HOST": HOST} if HOST else {})}
    done = subprocess.run(["docker", *args], capture_output=True, text=True, env=env, check=check, timeout=1800)  # noqa: S607
    return done.stdout.strip()


@pytest.fixture(scope="session")
def image(tmp_path_factory: pytest.TempPathFactory) -> str:
    context = tmp_path_factory.mktemp("runner-context")
    shutil.copy(REPO / "infrastructure/docker/runner/Dockerfile", context / "Dockerfile")
    shutil.copy(Path(supervisor.__file__), context / "supervisor.py")
    docker("build", "--tag", IMAGE, str(context))
    return IMAGE


@pytest.fixture
def sandbox(image: str) -> DockerSandbox:
    return DockerSandbox(DockerSandboxConfig(image=image, docker_host=HOST, ttl_seconds=120))


def leftover_containers() -> list[str]:
    return [
        name for name in docker("ps", "--all", "--filter", f"label={LABEL}=1", "--format", "{{.Names}}").split() if name
    ]


@pytest_asyncio.fixture(autouse=True)
async def no_container_is_ever_left_behind(image: str):
    yield
    # `--rm` and the explicit removal are asynchronous on the daemon side: allow a moment.
    for _ in range(50):
        if not leftover_containers():
            return
        await asyncio.sleep(0.2)
    pytest.fail(f"sandbox containers were left behind: {leftover_containers()}")


LINES = LinesChecker()
CONFIG = JudgeConfig(max_output_bytes=100_000)


async def judge(
    sandbox: DockerSandbox,
    source: str,
    *,
    language: str = "python",
    tests: list[tuple[str, str]] | None = None,
    time_limit_ms: int = 1000,
    memory_limit_mb: int = 64,
) -> JudgeReport:
    cases = [JudgeTest(input=i, expected=o, public=False) for i, o in (tests or [("2 3\n", "5\n")])]
    return await judge_tests(
        sandbox,
        language=get_language(language),
        source=source,
        tests=cases,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
        checker=LINES,
        config=CONFIG,
    )


async def assert_still_healthy(sandbox: DockerSandbox) -> None:
    report = await judge(sandbox, "a, b = map(int, input().split())\nprint(a + b)\n")
    assert report.verdict is Verdict.ACCEPTED, "the judge stopped working after the hostile submission"


SUM = {
    "python": "a, b = map(int, input().split())\nprint(a + b)\n",
    "javascript": "const [a, b] = require('fs').readFileSync(0, 'utf8').trim().split(/\\s+/).map(Number);\nconsole.log(a + b);\n",
    "cpp": "#include <iostream>\nint main(){ long long a, b; std::cin >> a >> b; std::cout << a + b << '\\n'; }\n",
}


# --- correctness and ordinary failures ----------------------------------------------------------------------------------


@pytest.mark.parametrize("language", ["python", "javascript", "cpp"])
async def test_an_accepted_solution_in_every_language(sandbox, language) -> None:
    report = await judge(sandbox, SUM[language], language=language, tests=[("2 3\n", "5\n"), ("10 20\n", "30\n")])
    assert (report.verdict, report.passed, report.total) == (Verdict.ACCEPTED, 2, 2)
    assert report.runtime_ms is not None
    assert report.memory_kb


async def test_wrong_answer(sandbox) -> None:
    report = await judge(sandbox, "print(42)\n")
    assert report.verdict is Verdict.WRONG_ANSWER


async def test_compilation_error_reports_the_compiler_output_and_runs_nothing(sandbox) -> None:
    report = await judge(sandbox, "int main( { return 0 }\n", language="cpp")
    assert report.verdict is Verdict.COMPILATION_ERROR
    assert report.compile_output
    assert "error" in report.compile_output.lower()
    assert report.outcomes == []


@pytest.mark.parametrize(
    ("language", "source"),
    [
        ("python", "raise ValueError('boom')\n"),
        ("python", "import sys\nsys.exit(3)\n"),
        ("javascript", "throw new Error('boom');\n"),
        ("cpp", "int main(){ return 3; }\n"),
        ("cpp", "int main(){ int* p = nullptr; *p = 1; return 0; }\n"),  # SIGSEGV
        ("cpp", "#include <cstdlib>\nint main(){ std::abort(); }\n"),  # SIGABRT
    ],
)
async def test_runtime_errors(sandbox, language, source) -> None:
    report = await judge(sandbox, source, language=language)
    assert report.verdict is Verdict.RUNTIME_ERROR
    await assert_still_healthy(sandbox)


# --- resource exhaustion ------------------------------------------------------------------------------------------------


async def test_a_program_that_sleeps_forever_times_out(sandbox) -> None:
    started = time.monotonic()
    report = await judge(sandbox, "import time\ntime.sleep(3600)\n", time_limit_ms=300)
    assert report.verdict is Verdict.TIME_LIMIT_EXCEEDED
    assert time.monotonic() - started < 30
    await assert_still_healthy(sandbox)


@pytest.mark.parametrize(
    ("language", "source"),
    [
        ("python", "while True:\n    pass\n"),
        ("cpp", "int main(){ volatile long x = 0; while (true) { x++; } }\n"),
        ("javascript", "while (true) {}\n"),
    ],
)
async def test_an_infinite_loop_is_stopped(sandbox, language, source) -> None:
    started = time.monotonic()
    report = await judge(sandbox, source, language=language, time_limit_ms=300)
    assert report.verdict is Verdict.TIME_LIMIT_EXCEEDED
    assert time.monotonic() - started < 30
    await assert_still_healthy(sandbox)


@pytest.mark.parametrize(
    ("language", "source"),
    [
        ("python", "blob = 'x' * (1024 * 1024 * 1024)\nprint(len(blob))\n"),
        # A single giant malloc is the wrong way to test this: the container gets `memory_slack_mb` (128 MB) of real
        # headroom above the 64 MB limit checked below, so a one-shot 1 GB request can be refused outright by the
        # allocator/kernel (strict overcommit) instead of growing RSS into the limit — malloc then returns NULL and
        # memset(NULL, ...) segfaults almost instantly (RUNTIME_ERROR, not MEMORY_LIMIT_EXCEEDED — seen in CI on a real
        # Docker daemon). Allocate and touch memory incrementally instead, like the JavaScript case below, so RSS is
        # guaranteed to cross the limit while the process is still alive for the supervisor's RSS watchdog to see.
        (
            "cpp",
            "#include <cstdlib>\n#include <cstring>\n"
            "int main(){ for(;;){ char* p = (char*)malloc(1<<20); if(!p) return 1; memset(p, 1, 1<<20); } }\n",
        ),
        ("javascript", "const a = []; while (true) a.push(new Array(1e6).fill(1));\n"),
    ],
)
async def test_memory_violations(sandbox, language, source) -> None:
    report = await judge(sandbox, source, language=language, memory_limit_mb=64, time_limit_ms=2000)
    assert report.verdict is Verdict.MEMORY_LIMIT_EXCEEDED
    await assert_still_healthy(sandbox)


async def test_a_flood_of_output_is_cut_off(sandbox) -> None:
    flood = "import sys\nwhile True:\n    sys.stdout.write('x' * 65536)\n"
    report = await judge(sandbox, flood)
    assert report.verdict is Verdict.RUNTIME_ERROR
    assert report.message == "Output limit exceeded"
    await assert_still_healthy(sandbox)


async def test_a_fork_bomb_is_contained(sandbox) -> None:
    bomb = "import os\nwhile True:\n    os.fork()\n"
    started = time.monotonic()
    report = await judge(sandbox, bomb, time_limit_ms=500)
    assert report.verdict in {Verdict.TIME_LIMIT_EXCEEDED, Verdict.RUNTIME_ERROR, Verdict.MEMORY_LIMIT_EXCEEDED}
    assert time.monotonic() - started < 60
    await assert_still_healthy(sandbox)  # the worker and the daemon survived


async def test_processes_left_running_do_not_survive_into_the_next_test(sandbox) -> None:
    """Test 1 leaves a background process behind; test 2 must not see it (it would if cleanup were skipped)."""
    program = (
        "import os, subprocess, sys\n"
        "def sleepers():\n"
        "    count = 0\n"
        "    for pid in os.listdir('/proc'):\n"
        "        try:\n"
        "            count += pid.isdigit() and 'sleep' in open(f'/proc/{pid}/cmdline').read()\n"
        "        except OSError:\n"
        "            pass\n"
        "    return count\n"
        "if sys.stdin.readline().strip() == 'spawn':\n"
        "    subprocess.Popen(['sleep', '600'], start_new_session=True)\n"
        "    print('spawned')\n"
        "else:\n"
        "    print(sleepers())\n"
    )
    report = await judge(sandbox, program, tests=[("spawn\n", "spawned\n"), ("count\n", "0\n")])
    assert report.verdict is Verdict.ACCEPTED, report.message


# --- escape attempts ----------------------------------------------------------------------------------------------------

NETWORK_PROBE = """
import socket
attempts = [
    lambda: socket.create_connection(("1.1.1.1", 53), timeout=2),      # the internet
    lambda: socket.create_connection(("8.8.8.8", 443), timeout=2),
    lambda: socket.create_connection(("127.0.0.1", 5432), timeout=2),  # PostgreSQL, if it were on this host
    lambda: socket.create_connection(("127.0.0.1", 6379), timeout=2),  # Redis
    lambda: socket.getaddrinfo("postgres", 5432),                      # service names of the application network
    lambda: socket.getaddrinfo("redis", 6379),
    lambda: socket.getaddrinfo("example.com", 80),
]
escaped = []
for index, attempt in enumerate(attempts):
    try:
        attempt()
        escaped.append(index)
    except OSError:
        pass
interfaces = sorted(__import__("os").listdir("/sys/class/net"))
print("blocked" if not escaped and interfaces == ["lo"] else f"ESCAPED {escaped} {interfaces}")
"""


async def test_network_access_is_impossible(sandbox) -> None:
    report = await judge(sandbox, NETWORK_PROBE, tests=[("", "blocked\n")], time_limit_ms=3000)
    assert report.verdict is Verdict.ACCEPTED, "the sandbox reached the network"


FILESYSTEM_PROBE = """
import os, stat

def can(action):
    try:
        action()
        return True
    except OSError:
        return False

def write(path):
    def go():
        with open(path, "w") as handle:
            handle.write("pwned")
    return go

escapes = []
checks = {
    "write /etc": lambda: can(write("/etc/pwned")),
    "write /usr": lambda: can(write("/usr/pwned")),
    "write /": lambda: can(write("/pwned")),
    "overwrite the supervisor": lambda: can(write("/opt/sjx/supervisor.py")),
    "docker socket present": lambda: os.path.exists("/var/run/docker.sock") or os.path.exists("/run/docker.sock"),
    "host mount present": lambda: any(os.path.exists(p) for p in ("/host", "/hostfs", "/mnt/host", "/var/lib/docker")),
    "read the container's main process": lambda: can(lambda: open("/proc/1/environ").read()),
    "signal the container's main process": lambda: can(lambda: os.kill(1, 9)),
    "list another user's home": lambda: can(lambda: os.listdir("/root")),
    "run as root": lambda: os.getuid() == 0 or os.geteuid() == 0,
    "any capability": lambda: any(
        line.startswith("CapEff") and line.split()[1].strip("0") for line in open("/proc/self/status")
    ),
    "new privileges allowed": lambda: not any(
        line.startswith("NoNewPrivs") and line.split()[1] == "1" for line in open("/proc/self/status")
    ),
    "secrets in the environment": lambda: any(
        key in os.environ for key in ("DATABASE_URL", "REDIS_URL", "JWT_SECRET", "POSTGRES_PASSWORD", "REDIS_PASSWORD")
    ),
    "unexpected files in the work dir": lambda: sorted(os.listdir("/work")) != ["main.py"],
    "setuid binary": lambda: any(
        os.stat(os.path.join(d, f)).st_mode & stat.S_ISUID
        for d in ("/bin", "/usr/bin", "/usr/local/bin")
        for f in os.listdir(d)
        if os.path.isfile(os.path.join(d, f))
    ),
}
for name, check in checks.items():
    if check():
        escapes.append(name)
print("blocked" if not escapes else "ESCAPED: " + "; ".join(escapes))
"""


async def test_the_filesystem_and_process_space_are_sealed(sandbox) -> None:
    report = await judge(sandbox, FILESYSTEM_PROBE, tests=[("", "blocked\n")], time_limit_ms=3000)
    assert report.verdict is Verdict.ACCEPTED, report.message


async def test_a_submission_cannot_read_another_submissions_files(sandbox) -> None:
    """Two sandboxes at once: the second must not be able to see the first's source, secret or work directory.

    Each container has its own `--read-only` root and private tmpfs mounts — "no bind mounts, no volumes, no host
    paths, ever" (docker_sandbox.py). So the only places a leak *could* show up are the writable mounts (`/work`,
    `/tmp`) and the process list (`/proc`, if the PID namespace were ever shared); everywhere else is the same
    read-only base image in both containers and can never contain either submission's data. A recursive `/**` glob of
    the whole filesystem previously scanned all of that identical, irrelevant image content too — slow (9-45s+ on a
    loaded CI runner, timing out) without checking anything a scoped scan doesn't already cover.
    """
    secret = "FIRST-SUBMISSIONS-SECRET-3c9e"
    holder = f"import time\nSECRET = {secret!r}\ntime.sleep(8)\n"
    spy = (
        "import glob, os\n"
        "found = []\n"
        "for path in glob.glob('/work/**', recursive=True) + glob.glob('/tmp/**', recursive=True) "
        "+ glob.glob('/proc/[0-9]*/cmdline'):\n"
        "    try:\n"
        f"        if os.path.isfile(path) and {secret!r} in open(path).read(): found.append(path)\n"
        "    except OSError:\n"
        "        pass\n"
        "print('blocked' if not found else 'ESCAPED ' + ' '.join(found))\n"
    )
    first = asyncio.create_task(judge(sandbox, holder, tests=[("", "")], time_limit_ms=10_000))
    await asyncio.sleep(1.5)  # the first sandbox is up and running its program
    report = await judge(sandbox, spy, tests=[("", "blocked\n")], time_limit_ms=5_000)
    assert report.verdict is Verdict.ACCEPTED
    await first


async def test_source_with_shell_metacharacters_is_data_not_a_command(sandbox) -> None:
    marker = "/tmp/injected"
    source = f"print('$(touch {marker}); `id`; ; | && \\\\')\nimport os\nprint(os.path.exists({marker!r}))\n"
    report = await judge(sandbox, source, tests=[("", "$(touch /tmp/injected); `id`; ; | && \\\nFalse\n")])
    assert report.verdict is Verdict.ACCEPTED, report.message


# --- lifecycle and cleanup ----------------------------------------------------------------------------------------------


async def test_the_container_is_removed_when_judging_is_cancelled(sandbox) -> None:
    task = asyncio.create_task(judge(sandbox, "import time\ntime.sleep(60)\n", time_limit_ms=30_000))
    await asyncio.sleep(3)
    assert leftover_containers(), "the sandbox should be running"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # the autouse fixture then verifies nothing is left


async def test_the_reaper_removes_the_container_of_a_worker_that_was_killed(sandbox) -> None:
    """Simulates `kill -9` of the worker: the session is opened and never closed."""
    manager = sandbox.session(get_language("python"), "print(1)\n", memory_limit_mb=64)
    await manager.__aenter__()
    assert len(leftover_containers()) == 1
    assert await sandbox.reap_stale(max_age_seconds=-1) == 1
    for _ in range(25):
        if not leftover_containers():
            break
        await asyncio.sleep(0.2)
    assert leftover_containers() == []
    await manager.__aexit__(None, None, None)  # the worker's own (late) cleanup must tolerate the container being gone


async def test_a_missing_image_is_a_sandbox_error_not_a_verdict() -> None:
    broken = DockerSandbox(DockerSandboxConfig(image="sahucodex/does-not-exist:0", docker_host=HOST))
    with pytest.raises(SandboxError):
        await judge(broken, "print(1)\n")
