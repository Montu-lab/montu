"""Voice anonymisation backends. `strength` is what a profile checks against."""
from __future__ import annotations

from typing import Protocol

import numpy as np


class VoiceAnonymiser(Protocol):
    strength: str  # "weak" | "qualified"  (qualified = has a recorded evaluation, plan §8.2)
    model_digest: str

    def anonymise(self, samples: np.ndarray, sr: int) -> np.ndarray: ...
