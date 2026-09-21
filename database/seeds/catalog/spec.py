"""Shared building blocks for the seed problem catalogue.

Every problem is a `Spec`: statement text, hand-written examples, and — crucially — a *reference solution*
(`solve`) plus a seeded input generator (`hidden`). Expected outputs for hidden tests are computed by running the
reference solution, so a test can never disagree with the code that produced it. A unit test additionally checks
that the hand-written example outputs in each statement equal the reference solution's output.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Example:
    input: str
    output: str
    explanation: str


@dataclass(frozen=True)
class Spec:
    slug: str
    title: str
    difficulty: str  # EASY | MEDIUM | HARD
    tags: tuple[str, ...]  # tag names (see TAGS)
    description: str  # Markdown
    input_format: str
    output_format: str
    constraints: str  # Markdown list
    examples: tuple[Example, ...]
    solve: Callable[[str], str]  # reference solution: stdin text -> stdout text (no trailing newline)
    hidden: Callable[[random.Random], list[str]]  # seeded generator of HIDDEN test inputs
    hints: tuple[str, ...]
    editorial: str
    time_complexity: str
    space_complexity: str
    time_limit_ms: int = 2000
    memory_limit_mb: int = 256
    starter_override: dict[str, str] | None = None


# The 23 topics required by the platform.
TAGS: tuple[str, ...] = (
    "Array",
    "String",
    "HashMap",
    "Two Pointer",
    "Sliding Window",
    "Stack",
    "Queue",
    "Linked List",
    "Tree",
    "Graph",
    "DFS",
    "BFS",
    "Binary Search",
    "Dynamic Programming",
    "Greedy",
    "Backtracking",
    "Heap",
    "Trie",
    "Union Find",
    "Bit Manipulation",
    "Math",
    "Sorting",
    "Searching",
)


def slugify(name: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in name.lower()).split())


def joined(*lines: object) -> str:
    """Build an input string: one item per line, terminated by a newline."""
    return "\n".join(str(line) for line in lines) + "\n"


def nums(values: list[int]) -> str:
    return " ".join(map(str, values))


# --- Starter code -------------------------------------------------------------------------------


def starter_code(spec: Spec) -> dict[str, str]:
    """Runnable skeletons that read stdin and write stdout, matching the judge's model."""
    if spec.starter_override:
        return dict(spec.starter_override)
    note = "Read the input exactly as described in the problem statement."
    return {
        "python": (
            "import sys\n\n\n"
            "def solve(data: str) -> str:\n"
            f"    # {note}\n"
            "    # TODO: parse `data`, compute the answer, and return the text to print.\n"
            '    return ""\n\n\n'
            'if __name__ == "__main__":\n'
            "    sys.stdout.write(solve(sys.stdin.read()))\n"
        ),
        "cpp": (
            "#include <bits/stdc++.h>\n"
            "using namespace std;\n\n"
            "int main() {\n"
            "    ios::sync_with_stdio(false);\n"
            "    cin.tie(nullptr);\n"
            f"    // {note}\n"
            "    // TODO: read the input, compute the answer and print it.\n"
            "    return 0;\n"
            "}\n"
        ),
        "javascript": (
            'const data = require("fs").readFileSync(0, "utf8");\n\n'
            "function solve(data) {\n"
            f"  // {note}\n"
            "  // TODO: parse `data`, compute the answer, and return the text to print.\n"
            '  return "";\n'
            "}\n\n"
            "process.stdout.write(solve(data));\n"
        ),
    }
