"""Output checkers: decide whether a program's output matches the expected output.

A checker is a pure function of (expected, actual), which is what keeps verdicts deterministic. New comparison rules
(floating point tolerance, special judges) implement `Checker` and are added with `register_checker`.
"""

from __future__ import annotations

from typing import Protocol


class Checker(Protocol):
    name: str

    def check(self, expected: str, actual: str) -> bool: ...


class ExactChecker:
    """Byte-for-byte equality. Strict: a missing trailing newline is a wrong answer."""

    name = "exact"

    def check(self, expected: str, actual: str) -> bool:
        return expected == actual


class WhitespaceChecker:
    """Equal token sequences: any run of whitespace (spaces, tabs, newlines) counts as one separator."""

    name = "whitespace"

    def check(self, expected: str, actual: str) -> bool:
        return expected.split() == actual.split()


class LinesChecker:
    """Line by line, ignoring `\r\n` vs `\n`, trailing whitespace on each line and trailing blank lines.

    Leading whitespace and the number and order of lines still matter. This is the default because it forgives the
    harmless differences (a final newline, Windows line endings) without hiding real formatting mistakes."""

    name = "lines"

    @staticmethod
    def _normalise(text: str) -> list[str]:
        lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
        while lines and not lines[-1]:
            lines.pop()
        return lines

    def check(self, expected: str, actual: str) -> bool:
        return self._normalise(expected) == self._normalise(actual)


DEFAULT_CHECKER = "lines"

_REGISTRY: dict[str, Checker] = {}


class UnknownCheckerError(LookupError):
    pass


def register_checker(checker: Checker) -> None:
    _REGISTRY[checker.name] = checker


def get_checker(name: str) -> Checker:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownCheckerError(f"unknown checker {name!r}; available: {', '.join(sorted(_REGISTRY))}") from None


for _checker in (ExactChecker(), WhitespaceChecker(), LinesChecker()):
    register_checker(_checker)
