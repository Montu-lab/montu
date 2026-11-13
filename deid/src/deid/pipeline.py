"""Per-call orchestration. Any exception in any stage drops the call; a dropped call writes a log
record and nothing else."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .asr import Transcriber
from .calllog import CallLog
from .lexicon import Lexicon
from .policy import PolicySet, Profile
from .voice import VoiceAnonymiser


@dataclass(frozen=True)
class CallAudio:
    agent: np.ndarray
    customer: np.ndarray
    sr: int
    source_bytes: bytes  # raw bytes of the input file(s), in order: hashed (keyed), never stored


@dataclass
class Deps:
    transcriber: Transcriber
    lexicon: Lexicon
    hmac_key: bytes
    voice: VoiceAnonymiser | None = None
    detector: Callable | None = None  # first-pass detector override (tests); leak scan always uses the real one
    language_mismatch_prob: float = 0.8


@dataclass(frozen=True)
class OutputDirs:
    staged: Path
    logs: Path


def process_call(call: CallAudio, profile: Profile, policy: PolicySet, deps: Deps,
                 dirs: OutputDirs) -> CallLog:
    raise NotImplementedError
