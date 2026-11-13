"""Audio and transcript redaction."""
from __future__ import annotations

import numpy as np

from .detect.detectors import SEVERITY
from .types import Entity, Word

TONE_HZ = 1000.0
TONE_PEAK = 0.1  # -20 dBFS


def plan_spans(spans_ms: list[tuple[int, int]], channel_ms: int, pad_before_ms: int,
               pad_after_ms: int) -> list[tuple[int, int]]:
    """Pad, clip to [0, channel_ms], merge overlaps. Returns sorted, disjoint spans."""
    padded = sorted((max(0, s - pad_before_ms), min(channel_ms, e + pad_after_ms)) for s, e in spans_ms)
    out: list[list[int]] = []
    for s, e in padded:
        if e <= s:
            continue
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def apply_audio(samples: np.ndarray, sr: int, spans_ms: list[tuple[int, int]], fill: str) -> np.ndarray:
    """fill: 'silence' or 'tone' (1 kHz sine at -20 dBFS). Returns a new array."""
    if fill not in ("silence", "tone"):
        raise ValueError("fill must be silence or tone")
    y = np.array(samples, dtype=np.float32, copy=True)
    for s, e in spans_ms:
        a, b = int(s * sr / 1000), min(len(y), int(np.ceil(e * sr / 1000)))
        if b <= a:
            continue
        if fill == "silence":
            y[a:b] = 0.0
        else:
            t = np.arange(b - a) / sr
            y[a:b] = (TONE_PEAK * np.sin(2 * np.pi * TONE_HZ * t)).astype(np.float32)
    return y


def regions(entities: list[Entity]) -> list[tuple[int, int, object]]:
    """Merge overlapping word ranges; each region takes its most severe category."""
    out: list[list] = []
    for e in sorted(entities, key=lambda e: (e.word_start, e.word_end)):
        if out and e.word_start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e.word_end)
            if SEVERITY.index(e.category) < SEVERITY.index(out[-1][2]):
                out[-1][2] = e.category
        else:
            out.append([e.word_start, e.word_end, e.category])
    return [tuple(r) for r in out]


def redact_transcript_with_times(words: list[Word], entities: list[Entity]) -> list[tuple[str, int, int]]:
    regs = {r[0]: r for r in regions(entities)}
    out, i = [], 0
    while i < len(words):
        if i in regs:
            s, e, cat = regs[i]
            out.append((f"[{cat.value}]", words[s].start_ms, words[e].end_ms))
            i = e + 1
        else:
            out.append((words[i].text, words[i].start_ms, words[i].end_ms))
            i += 1
    return out


def redact_transcript(words: list[Word], entities: list[Entity]) -> list[str]:
    """Replace each entity's words with one typed token, e.g. '[NAME]'."""
    return [t for t, _, _ in redact_transcript_with_times(words, entities)]
