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
