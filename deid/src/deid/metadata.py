"""Batch metadata: an allow-list. Anything not listed rejects the batch."""
from __future__ import annotations

from dataclasses import dataclass

from .policy import PolicyError, PolicySet

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
    pairing: str | None  # dual-mono: "{id}_agent.wav|{id}_customer.wav" style pattern, or None for stereo


def parse_batch_metadata(raw: dict, policy: PolicySet) -> BatchMeta:
    if not isinstance(raw, dict):
        raise MetadataRejected("unknown_key")
    if set(raw) - ALLOWED_KEYS:
        raise MetadataRejected("unknown_key")
    if REQUIRED_KEYS - set(raw):
        raise MetadataRejected("missing_key")
    code = raw["profile_code"]
    try:
        policy.profile(code if isinstance(code, str) else "")
    except PolicyError:
        raise MetadataRejected("unknown_profile") from None
    cm = raw["channel_map"]
    if not (isinstance(cm, dict) and set(cm) == {"agent", "customer"}
            and all(isinstance(v, int) and not isinstance(v, bool) for v in cm.values())
            and sorted(cm.values()) == [0, 1]):
        raise MetadataRejected("bad_channel_map")
    pairing = raw.get("pairing")
    if pairing is not None and not (isinstance(pairing, str) and pairing.count("|") == 1
                                    and pairing.count("{id}") == 2):
        raise MetadataRejected("bad_pairing")
    return BatchMeta(code, dict(cm), pairing)
