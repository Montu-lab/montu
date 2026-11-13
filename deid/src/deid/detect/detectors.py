"""Identifier detection over one channel's word stream."""
from __future__ import annotations

from dataclasses import dataclass

from ..lexicon import Lexicon
from ..types import Channel, Entity, Word


@dataclass(frozen=True)
class DetectConfig:
    digit_catch_all: int = 4
    low_conf: float = 0.5
    low_conf_window: int = 2
    greeting_window_ms: int = 20_000
    unclear_run: int = 3


def detect_channel(words: list[Word], lang: str, channel: Channel, lexicon: Lexicon,
                   cfg: DetectConfig = DetectConfig()) -> list[Entity]:
    raise NotImplementedError
