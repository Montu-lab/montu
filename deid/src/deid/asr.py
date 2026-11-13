"""Local ASR. Loads a model from a local directory only; never a hub id, never a download."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from .types import Channel, Word


@dataclass(frozen=True)
class Transcript:
    words: list[Word]
    language: str
    language_prob: float


class Transcriber(Protocol):
    model_digest: str

    def transcribe(self, samples: np.ndarray, sr: int, channel: Channel) -> Transcript: ...


class FasterWhisperTranscriber:
    def __init__(self, model_dir: str | Path, device: str = "auto", compute_type: str = "default"):
        raise NotImplementedError
