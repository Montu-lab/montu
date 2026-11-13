"""Audio and transcript redaction."""
from __future__ import annotations

import numpy as np

from .types import Entity, Word


def plan_spans(spans_ms: list[tuple[int, int]], channel_ms: int, pad_before_ms: int,
               pad_after_ms: int) -> list[tuple[int, int]]:
    """Pad, clip to [0, channel_ms], merge overlaps. Returns sorted, disjoint spans."""
    raise NotImplementedError


def apply_audio(samples: np.ndarray, sr: int, spans_ms: list[tuple[int, int]], fill: str) -> np.ndarray:
    """fill: 'silence' or 'tone' (1 kHz sine at -20 dBFS). Returns a new array."""
    raise NotImplementedError


def redact_transcript(words: list[Word], entities: list[Entity]) -> list[str]:
    """Replace each entity's words with one typed token, e.g. '[NAME]'."""
    raise NotImplementedError
