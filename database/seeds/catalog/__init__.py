"""The seed catalogue: 30 original problems (10 EASY, 12 MEDIUM, 8 HARD) covering 23 topics."""

from .easy import EASY
from .hard import HARD
from .medium import MEDIUM
from .spec import TAGS, Example, Spec, slugify, starter_code

ALL_PROBLEMS: list[Spec] = [*EASY, *MEDIUM, *HARD]

__all__ = ["ALL_PROBLEMS", "EASY", "HARD", "MEDIUM", "TAGS", "Example", "Spec", "slugify", "starter_code"]
