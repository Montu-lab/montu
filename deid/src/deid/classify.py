"""Call-level exclusion: decides whether a call is dropped. Runs before anything is written."""
from __future__ import annotations

from .policy import Profile
from .types import Channel, Decision, Entity, Word


def classify_call(words: dict[Channel, list[Word]], entities: list[Entity], profile: Profile,
                  lang: str) -> Decision:
    raise NotImplementedError
