"""Batch metadata: an allow-list. Anything not listed rejects the batch."""
from __future__ import annotations

from dataclasses import dataclass

from .policy import PolicySet

ALLOWED_KEYS = frozenset({"profile_code", "channel_map", "pairing"})
REQUIRED_KEYS = frozenset({"profile_code", "channel_map"})


class MetadataRejected(Exception):
    """reason: unknown_key | missing_key | unknown_profile | bad_channel_map | bad_pairing.
    The message never repeats the offending value: it may be a client name."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class BatchMeta:
    profile_code: str
    channel_map: dict[str, int]  # {"agent": 0, "customer": 1}
    pairing: str | None  # glob suffix pattern for dual-mono pairs, e.g. "{id}_agent.wav|{id}_customer.wav"


def parse_batch_metadata(raw: dict, policy: PolicySet) -> BatchMeta:
    raise NotImplementedError
