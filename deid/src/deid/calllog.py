"""The per-call log. No free-text field exists: every field is an enum, an int, a float or a digest.
Construction goes through CallLogBuilder, which refuses anything else."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .types import Category, Channel, Detector, DropReason


class LogFieldError(Exception):
    pass


class ModelSlot(str, Enum):
    ASR = "asr"
    NER = "ner"
    VOICE = "voice"
    CLASSIFIER = "classifier"


class Decision(str, Enum):
    STAGED = "released_to_staging"
    DROPPED = "dropped"


# Exception classes recorded by name. Anything else is recorded as "OtherError". Never the message.
KNOWN_ERRORS = frozenset({
    "RuntimeError", "ValueError", "KeyError", "IndexError", "TypeError", "OSError",
    "MemoryError", "NotImplementedError", "AssertionError", "TimeoutError", "NetworkBlocked",
})


@dataclass(frozen=True)
class Removal:
    category: Category
    channel: Channel
    start_ms: int
    end_ms: int
    detector: Detector
    confidence: float


@dataclass(frozen=True)
class CallLog:
    call_id: str
    profile_code: str
    policy_version: str
    pipeline_version: str
    model_versions: tuple[tuple[ModelSlot, str], ...]
    decision: Decision
    drop_reason: DropReason | None
    error_class: str | None
    removals: tuple[Removal, ...]

    def to_json(self) -> str:
        raise NotImplementedError


class CallLogBuilder:
    def __init__(self, *, call_id: str, profile_code: str, policy_version: str, pipeline_version: str,
                 model_versions: dict):
        raise NotImplementedError

    def add_removal(self, *, category, channel, start_ms, end_ms, detector, confidence) -> None:
        raise NotImplementedError

    def drop(self, reason) -> None:
        raise NotImplementedError

    def error(self, exc: BaseException) -> None:
        raise NotImplementedError

    def build(self) -> CallLog:
        raise NotImplementedError
