"""Builds the system/user prompts for every AI feature.

The only problem data that ever appears here is a `ProblemPublic` — the exact shape the public problem API returns.
There is no field on it for hidden tests or the editorial (see app/modules/problems/schemas.py), so this module
cannot leak them even by a future bug here; the leak would have to happen where `ProblemPublic` itself is built,
which is covered by its own tests.
"""

from __future__ import annotations

from app.modules.problems.schemas import ProblemPublic

RULES = (
    "You are SahuCodeX AI, a coding assistant built into the SahuCodeX competitive-programming platform.\n"
    "Follow these rules at all times:\n"
    "- You are an assistant, not the judge. SahuJudge alone decides whether a submission is correct by actually "
    "running it; never say code 'will pass', 'is correct', or 'is accepted' — describe it as 'looks right to me' at "
    "most, and say the judge is the real answer.\n"
    "- You have not been given any hidden test cases and must never invent or guess one.\n"
    "- Answer in Markdown. Put code in fenced code blocks with a language tag.\n"
    "- Be concise and specific rather than generic.\n"
)


def _problem_block(problem: ProblemPublic | None) -> str:
    if problem is None:
        return ""
    parts = [f"Problem: {problem.title} ({problem.difficulty})", problem.description]
    if problem.constraints:
        parts.append(f"Constraints:\n{problem.constraints}")
    if problem.input_format:
        parts.append(f"Input format:\n{problem.input_format}")
    if problem.output_format:
        parts.append(f"Output format:\n{problem.output_format}")
    for i, example in enumerate(problem.examples, start=1):
        parts.append(f"Example {i} input:\n{example.input}\nExample {i} output:\n{example.output}")
    return "\n\n".join(parts)


def _code_block(language: str, code: str) -> str:
    return f"Language: {language}\nCode:\n```{language}\n{code}\n```"


def hint_prompt(problem: ProblemPublic, language: str, code: str, previous_hints: list[str]) -> tuple[str, str]:
    system = RULES + (
        "\nTask: give exactly ONE short, progressive hint toward solving the problem below — a nudge, not the "
        "solution, and never working code. If earlier hints are listed, go a step further than the last one and "
        "never repeat one."
    )
    prior = "\n".join(f"{i}. {hint}" for i, hint in enumerate(previous_hints, start=1)) or "(none yet)"
    prompt = (
        f"{_problem_block(problem)}\n\n{_code_block(language, code)}\n\n"
        f"Hints already given:\n{prior}\n\nGive the next hint."
    )
    return system, prompt


def explain_prompt(problem: ProblemPublic | None, language: str, code: str) -> tuple[str, str]:
    system = RULES + (
        "\nTask: explain the code below — what it does, the approach/algorithm, the key logic, and its time and "
        "space complexity."
    )
    prompt = "\n\n".join(part for part in (_problem_block(problem), _code_block(language, code)) if part)
    return system, prompt + "\n\nExplain this code."


def review_prompt(problem: ProblemPublic | None, language: str, code: str) -> tuple[str, str]:
    system = RULES + (
        "\nTask: review the code below using exactly these Markdown headings, in order: `## Correctness`, "
        "`## Potential bugs and edge cases`, `## Time and space complexity`, `## Readability`, "
        "`## Possible optimisations`.\n"
        "Under `## Correctness`, your first sentence must be exactly: \"I can't run this code, so this is only my "
        'reading of it.\' Then describe what the logic appears to do. Never write the words "correct", "correctly", '
        '"will pass" or "will work" about the code as a whole.\n'
        "Only list a bug or edge case if you can point to the specific line and a concrete input that breaks it; if "
        "you cannot, write 'None found by reading.' Do not invent problems. Be specific, not generic."
    )
    prompt = "\n\n".join(part for part in (_problem_block(problem), _code_block(language, code)) if part)
    return system, prompt + "\n\nReview this code."


def _rag_block(related: list[tuple[str, str, str]]) -> str:
    """`related` is (slug, title, difficulty) triples from a RAG similarity search — see app.modules.rag.service.
    Given only as reference material the model may mention; it is never told these are the "right" answer to
    anything, since a semantic match is not the same as "the ideal problem for this learner"."""
    if not related:
        return ""
    lines = "\n".join(f"- {title} ({difficulty}), slug: {slug}" for slug, title, difficulty in related)
    return (
        "Problems on this platform that may be relevant to what the learner is asking about (only mention one if "
        "it genuinely helps; never invent a problem or slug that is not in this list):\n" + lines
    )


def chat_system_prompt(problem: ProblemPublic | None, related: list[tuple[str, str, str]] | None = None) -> str:
    system = RULES + (
        "\nYou are having an open-ended conversation with a learner. "
        "Ask a clarifying question if the request is ambiguous."
    )
    block = _problem_block(problem)
    if block:
        return f"{system}\n\n{block}"
    rag_block = _rag_block(related or [])
    return f"{system}\n\n{rag_block}" if rag_block else system
