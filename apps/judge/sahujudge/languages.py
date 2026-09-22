"""Language runners as data.

Adding a language means adding a toolchain to the runner image (infrastructure/docker/runner/Dockerfile, and for the
serverless backend the Vercel Sandbox snapshot — see docs/judge.md) and one `LanguageSpec` here, and enabling its row
in `programming_languages` (database/migrations) — no judge logic changes.

Commands are fixed argument vectors (no shell), so nothing a user submits is ever interpreted as a command.
Source is written to `/work/<source_name>` inside the sandbox; the compiled program, if any, to `/work/main`
(`csharp` is the one exception: `dotnet build` needs a project file, so its output is `/work/out/sjx.dll`, and the
runner image/snapshot must bake an empty console project - `sjx.csproj` - at `/work` for it to build against).
"""

from __future__ import annotations

from dataclasses import dataclass

WORKDIR = "/work"


@dataclass(frozen=True)
class LanguageSpec:
    key: str
    source_name: str
    run: tuple[str, ...]
    compile: tuple[str, ...] | None = None
    # Interpreted languages start slower and run slower; the problem's limit is multiplied so a correct Python or
    # Node solution is not failed for the language's speed. The multiplier is stored with each result.
    time_multiplier: float = 1.0
    compile_time_ms: int = 20_000
    # Compilers need more memory than the problem's limit. The container is sized max(limit + slack, this).
    min_container_memory_mb: int = 128
    # See RunLimits.nofile: most compilers/runtimes are fine with the default; some (observed: .NET's MSBuild and,
    # separately, the CoreCLR runtime) need far more open file descriptors just to start up at all.
    compile_nofile_limit: int = 128
    run_nofile_limit: int = 128
    # RLIMIT_FSIZE for `run` (normally the problem's own output cap, tight by design - a wrong/looping program must
    # not be able to fill the disk). Some runtimes (observed: CoreCLR, which mmaps its own .dll files) fail to even
    # start under a cap that small; only such runtimes get a bigger one here. None -> use the output cap as before.
    run_fsize_bytes: int | None = None
    env: tuple[tuple[str, str], ...] = ()

    @property
    def source_path(self) -> str:
        return f"{WORKDIR}/{self.source_name}"


LANGUAGES: dict[str, LanguageSpec] = {
    spec.key: spec
    for spec in (
        LanguageSpec(
            key="python",
            source_name="main.py",
            run=("python3", "-B", f"{WORKDIR}/main.py"),
            time_multiplier=3.0,
            env=(("PYTHONHASHSEED", "0"), ("PYTHONIOENCODING", "utf-8"), ("PYTHONDONTWRITEBYTECODE", "1")),
        ),
        LanguageSpec(
            key="javascript",
            source_name="main.js",
            run=("node", f"{WORKDIR}/main.js"),
            time_multiplier=2.0,
            min_container_memory_mb=256,
        ),
        LanguageSpec(
            key="cpp",
            source_name="main.cpp",
            compile=(
                "g++",
                "-std=c++17",
                "-O2",
                "-pipe",
                "-fmax-errors=20",
                "-o",
                f"{WORKDIR}/main",
                f"{WORKDIR}/main.cpp",
            ),
            run=(f"{WORKDIR}/main",),
            min_container_memory_mb=768,
        ),
        LanguageSpec(
            key="c",
            source_name="main.c",
            compile=("gcc", "-std=c17", "-O2", "-pipe", "-fmax-errors=20", "-o", f"{WORKDIR}/main", f"{WORKDIR}/main.c"),
            run=(f"{WORKDIR}/main",),
            min_container_memory_mb=768,
        ),
        LanguageSpec(
            key="java",
            source_name="Main.java",
            # The class file lands next to the source (`-d WORKDIR`); the class must be named `Main`.
            compile=("javac", "-d", WORKDIR, f"{WORKDIR}/Main.java"),
            run=("java", "-XX:+UseSerialGC", "-Xshare:auto", "-cp", WORKDIR, "Main"),
            time_multiplier=2.0,
            compile_time_ms=30_000,
            min_container_memory_mb=384,
        ),
        LanguageSpec(
            key="csharp",
            source_name="Program.cs",
            # A throwaway console project: `dotnet run` alone needs a restore, which needs network. `dotnet build`
            # against a prepared project (baked into the snapshot at WORKDIR) only needs to compile this one file.
            compile=("dotnet", "build", "-c", "Release", "--no-restore", "-o", f"{WORKDIR}/out", f"{WORKDIR}"),
            run=("dotnet", f"{WORKDIR}/out/sjx.dll"),
            time_multiplier=1.5,
            compile_time_ms=30_000,
            min_container_memory_mb=512,
            # MSBuild opens far more file descriptors than a typical compiler just to evaluate the project; under the
            # default 128 it fails confusingly (OOM-killed, "assembly not found") well inside its CPU/wall/memory
            # budget. 1024 is comfortably above what a `dotnet build` of one file needs and still far below what
            # would let a fork bomb do real damage.
            compile_nofile_limit=1024,
            run_nofile_limit=1024,
            # CoreCLR mmaps its own shared-framework .dlls (System.Private.CoreLib.dll etc.) when it starts; under the
            # tight RLIMIT_FSIZE a submission's own output gets (by design - see run_fsize_bytes above), that mmap
            # fails and the runtime dies before printing anything ("Out Of Memory" / "0x8007000E", despite using well
            # under a megabyte of actual RSS). 64 MiB is generous headroom for the runtime's own files; a submission's
            # program output is still capped by --max-output regardless of this.
            run_fsize_bytes=64 * 1024 * 1024,
            # Without these, the .NET SDK's first-run/telemetry/update-check machinery tries to phone home; in a
            # network-denied sandbox that hangs until the wall-clock limit kills it (seen as TIMEOUT with ~0 CPU time
            # used - the process was blocked on I/O, not compiling).
            env=(
                ("DOTNET_CLI_TELEMETRY_OPTOUT", "1"),
                ("DOTNET_NOLOGO", "1"),
                ("DOTNET_SKIP_FIRST_TIME_EXPERIENCE", "1"),
                ("DOTNET_MULTILEVEL_LOOKUP", "0"),
                ("NUGET_XMLDOC_MODE", "skip"),
            ),
        ),
        LanguageSpec(
            key="go",
            source_name="main.go",
            compile=("go", "build", "-o", f"{WORKDIR}/main", f"{WORKDIR}/main.go"),
            run=(f"{WORKDIR}/main",),
            compile_time_ms=30_000,
            min_container_memory_mb=384,
            env=(("GOCACHE", "/tmp/sjx-gocache"), ("GOFLAGS", "-mod=mod")),
        ),
        LanguageSpec(
            key="rust",
            source_name="main.rs",
            compile=("rustc", "-O", "--edition", "2021", "-o", f"{WORKDIR}/main", f"{WORKDIR}/main.rs"),
            run=(f"{WORKDIR}/main",),
            compile_time_ms=30_000,
            min_container_memory_mb=512,
        ),
        LanguageSpec(
            key="typescript",
            source_name="main.ts",
            # Node's own type-stripping (stable since Node 22): erases type syntax without checking it and runs the
            # result directly, no separate compiler/bundler needed. Like esbuild's `transform`, this does not
            # type-check - which is what a judge wants (fast, faithful-to-Node execution), and matches how
            # competitive-programming judges have always treated TS as "JS plus types".
            run=("node", "--no-warnings", "--experimental-strip-types", f"{WORKDIR}/main.ts"),
            time_multiplier=2.0,
            min_container_memory_mb=256,
        ),
        LanguageSpec(
            key="php",
            source_name="main.php",
            run=("php", f"{WORKDIR}/main.php"),
            time_multiplier=3.0,
            min_container_memory_mb=192,
        ),
    )
}


class UnsupportedLanguageError(LookupError):
    pass


def get_language(key: str) -> LanguageSpec:
    try:
        return LANGUAGES[key]
    except KeyError:
        raise UnsupportedLanguageError(f"no runner for language {key!r}") from None
