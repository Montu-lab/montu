"""Local ASR. Loads a model from a local directory only; never a hub id, never a download."""
from __future__ import annotations

import hashlib
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


def dir_digest(d: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in d.rglob("*") if p.is_file() and ".cache" not in p.parts):
        h.update(str(f.relative_to(d)).encode() + b"\0" + hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest()


def resample(x: np.ndarray, sr: int, target: int = 16000) -> np.ndarray:
    """Linear-interpolation resampler. Adequate for 8 kHz -> 16 kHz upsampling (no aliasing on the way up)."""
    if sr == target:
        return x.astype(np.float32)
    n = int(round(len(x) * target / sr))
    return np.interp(np.arange(n) * sr / target, np.arange(len(x)), x).astype(np.float32)


class FasterWhisperTranscriber:
    def __init__(self, model_dir: str | Path, device: str = "auto", compute_type: str = "default",
                 beam_size: int = 5):
        p = Path(model_dir)
        if not p.is_dir() or not (p / "model.bin").exists():
            raise ValueError(f"ASR model must be a local directory containing model.bin; got {model_dir!r}")
        from faster_whisper import WhisperModel  # local import: the package must import without it

        self.model = WhisperModel(str(p), device=device, compute_type=compute_type, local_files_only=True)
        self.model_digest = dir_digest(p)
        self.beam_size = beam_size

    def transcribe(self, samples: np.ndarray, sr: int, channel: Channel) -> Transcript:
        audio = resample(samples, sr)
        # No VAD filter: words the VAD drops are untranscribed audio, which the pipeline then has to treat as
        # unreadable. Hallucinated words on silence only add redactions.
        segments, info = self.model.transcribe(audio, beam_size=self.beam_size, word_timestamps=True,
                                               vad_filter=False, condition_on_previous_text=False)
        words = []
        for seg in segments:
            for w in seg.words or []:
                text = w.word.strip()
                if text:
                    words.append(Word(text, int(w.start * 1000), int(w.end * 1000), float(w.probability), channel))
        return Transcript(words, info.language, float(info.language_probability))
