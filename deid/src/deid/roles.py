"""What the Montu operator may read: out/logs and out/released. A convenience, not a control:
the control is the BPO's IAM on those prefixes (plan §4)."""
from __future__ import annotations

from pathlib import Path


class AccessRefused(Exception):
    pass


class MontuView:
    def __init__(self, out_root: Path):
        raise NotImplementedError

    def read(self, rel_path: str) -> bytes:
        raise NotImplementedError

    def list(self) -> list[str]:
        raise NotImplementedError
