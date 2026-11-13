"""Shared helpers. Evidence class: UNIT. Synthetic word streams stand in for ASR output; nothing
here says anything about real audio or real ASR."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deid.types import Channel, Word  # noqa: E402

POLICY_DIR = Path(__file__).resolve().parents[1] / "policies"


def mkwords(text: str, channel: Channel = Channel.CUSTOMER, start_ms: int = 0, step_ms: int = 300,
            prob: float = 0.95, low: set[int] | None = None) -> list[Word]:
    """One Word per whitespace token, `step_ms` apart, each lasting step_ms - 50.
    Indices in `low` get probability 0.2."""
    out = []
    for i, tok in enumerate(text.split()):
        s = start_ms + i * step_ms
        out.append(Word(tok, s, s + step_ms - 50, 0.2 if low and i in low else prob, channel))
    return out


@pytest.fixture(scope="session")
def policy():
    from deid.policy import load_policy
    return load_policy(POLICY_DIR)
