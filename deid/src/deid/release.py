"""Approval and release. Nothing reaches out/released/ without a recorded approval of the exact manifest."""
from __future__ import annotations

from pathlib import Path


class ReleaseRefused(Exception):
    """reason: no_approval | rejected | manifest_changed | dropped_call_has_output | no_eval_report
    | eval_failing"""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def record_approval(out_root: Path, batch_id: str, manifest_digest: str, reviewer: str,
                    approved: bool, reason_code: str) -> None:
    raise NotImplementedError


def release(out_root: Path, batch_id: str, eval_report: dict | None) -> list[str]:
    """Copies approved staged outputs to out/released/<batch_id>/. Returns released call ids."""
    raise NotImplementedError
