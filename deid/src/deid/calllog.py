"""The per-call log. No free-text field exists: every field is an enum, an int, a float or a digest.
Construction goes through CallLogBuilder, which refuses anything else."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum

from .policy import PROFILE_CODE, SEMVER
from .types import Category, Channel, Detector, DropReason

HEX64 = re.compile(r"^[0-9a-f]{64}$")


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
    "FileNotFoundError", "PermissionError", "ZeroDivisionError",
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

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "profile_code": self.profile_code,
            "policy_version": self.policy_version,
            "pipeline_version": self.pipeline_version,
            "model_versions": {k.value: v for k, v in self.model_versions},
            "decision": self.decision.value,
            "drop_reason": self.drop_reason.value if self.drop_reason else None,
            "error_class": self.error_class,
            "removals": [{"category": r.category.value, "channel": r.channel.value, "start_ms": r.start_ms,
                          "end_ms": r.end_ms, "detector": r.detector.value, "confidence": r.confidence}
                         for r in self.removals],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


class CallLogBuilder:
    def __init__(self, *, call_id: str, profile_code: str, policy_version: str, pipeline_version: str,
                 model_versions: dict):
        if not (isinstance(call_id, str) and HEX64.match(call_id)):
            raise LogFieldError("call_id must be 64 lowercase hex")
        if not (isinstance(profile_code, str) and PROFILE_CODE.match(profile_code)):
            raise LogFieldError("profile_code has the wrong shape")
        for v in (policy_version, pipeline_version):
            if not (isinstance(v, str) and SEMVER.match(v)):
                raise LogFieldError("version must be semver")
        if not isinstance(model_versions, dict):
            raise LogFieldError("model_versions must be a dict")
        for k, v in model_versions.items():
            if not isinstance(k, ModelSlot) or not (isinstance(v, str) and HEX64.match(v)):
                raise LogFieldError("model_versions: ModelSlot -> 64 hex")
        self._head = (call_id, profile_code, policy_version, pipeline_version,
                      tuple(sorted(model_versions.items(), key=lambda kv: kv[0].value)))
        self._removals: list[Removal] = []
        self._drop: DropReason | None = None
        self._error: str | None = None

    def add_removal(self, *, category, channel, start_ms, end_ms, detector, confidence) -> None:
        if not isinstance(category, Category) or not isinstance(channel, Channel) \
                or not isinstance(detector, Detector):
            raise LogFieldError("category, channel and detector must be enums")
        if not (_int(start_ms) and _int(end_ms) and end_ms >= start_ms):
            raise LogFieldError("timings must be non-negative ints, end >= start")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise LogFieldError("confidence must be in [0, 1]")
        self._removals.append(Removal(category, channel, start_ms, end_ms, detector, round(float(confidence), 4)))

    def drop(self, reason) -> None:
        if not isinstance(reason, DropReason):
            raise LogFieldError("drop reason must be a DropReason")
        if self._drop is None:
            self._drop = reason

    def error(self, exc: BaseException) -> None:
        name = type(exc).__name__
        self._error = name if name in KNOWN_ERRORS else "OtherError"
        self.drop(DropReason.STAGE_ERROR)

    @property
    def dropped(self) -> bool:
        return self._drop is not None

    def build(self) -> CallLog:
        dropped = self._drop is not None
        return CallLog(*self._head, decision=Decision.DROPPED if dropped else Decision.STAGED,
                       drop_reason=self._drop, error_class=self._error,
                       removals=() if dropped else tuple(self._removals))
