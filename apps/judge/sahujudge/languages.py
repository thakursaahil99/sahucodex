"""Language runners as data.

Adding a language means adding a toolchain to the runner image (infrastructure/docker/runner/Dockerfile) and one
`LanguageSpec` here, and enabling its row in `programming_languages` — no judge logic changes.

Commands are fixed argument vectors (no shell), so nothing a user submits is ever interpreted as a command.
Source is written to `/work/<source_name>` inside the sandbox; the compiled program, if any, to `/work/main`.
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
    )
}


class UnsupportedLanguageError(LookupError):
    pass


def get_language(key: str) -> LanguageSpec:
    try:
        return LANGUAGES[key]
    except KeyError:
        raise UnsupportedLanguageError(f"no runner for language {key!r}") from None
