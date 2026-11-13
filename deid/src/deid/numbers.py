"""Spoken numbers -> digit strings, with exact word-index provenance."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NumberRun:
    digits: str
    start: int  # inclusive word index
    end: int  # inclusive word index


def find_number_runs(words: list[str], lang: str) -> list[NumberRun]:
    raise NotImplementedError
