"""Letter-by-letter spelling -> letters, with word-index provenance."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpelledRun:
    letters: str
    start: int
    end: int


def find_spelled_runs(words: list[str], lang: str, min_letters: int = 3) -> list[SpelledRun]:
    raise NotImplementedError
