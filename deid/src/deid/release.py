"""Approval and release. Nothing reaches out/released/ without a recorded approval of the exact manifest."""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from .manifest import manifest_digest, verify_manifest

_CODE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


class ReleaseRefused(Exception):
    """reason: no_approval | rejected | manifest_changed | dropped_call_has_output | unknown_output
    | no_eval_report | eval_failing"""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def _approvals(out_root: Path, batch_id: str) -> Path:
    return Path(out_root) / "logs" / f"{batch_id}.approvals.jsonl"


def record_approval(out_root: Path, batch_id: str, manifest_digest: str, reviewer: str,
                    approved: bool, reason_code: str) -> None:
    """reviewer and reason_code are short codes, never names or notes (this file is Montu-readable)."""
    if not (_CODE.match(batch_id) or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", batch_id)):
        raise ValueError("bad batch id")
    if not _CODE.match(reviewer) or not _CODE.match(reason_code) or not re.fullmatch(r"[0-9a-f]{64}",
                                                                                      manifest_digest):
        raise ValueError("reviewer and reason_code must be short codes; digest must be hex")
    rec = {"batch_id": batch_id, "manifest_digest": manifest_digest, "reviewer": reviewer,
           "approved": bool(approved), "reason_code": reason_code, "at": int(time.time())}
    with open(_approvals(out_root, batch_id), "a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def release(out_root: Path, batch_id: str, eval_report: dict | None) -> list[str]:
    """Copies approved staged outputs to out/released/<batch_id>/. Returns released call ids."""
    out_root = Path(out_root)
    logs = out_root / "logs"
    staged = out_root / "staged" / batch_id
    manifest = json.loads((logs / f"{batch_id}.manifest.json").read_text())
    ap = _approvals(out_root, batch_id)
    recs = [json.loads(x) for x in ap.read_text().splitlines() if x.strip()] if ap.exists() else []
    if not recs:
        raise ReleaseRefused("no_approval")
    last = recs[-1]
    if not last["approved"]:
        raise ReleaseRefused("rejected", last["reason_code"])
    if last["manifest_digest"] != manifest_digest(manifest) or verify_manifest(staged, manifest):
        raise ReleaseRefused("manifest_changed")
    calls = [json.loads(x) for x in (logs / f"{batch_id}.calls.jsonl").read_text().splitlines() if x.strip()]
    ok = {c["call_id"] for c in calls if c["decision"] == "released_to_staging"}
    dropped = {c["call_id"] for c in calls if c["decision"] == "dropped"}
    for f in manifest["files"]:
        cid = f["call_id"]
        if cid in dropped:
            raise ReleaseRefused("dropped_call_has_output")
        if cid not in ok:
            raise ReleaseRefused("unknown_output")
    if not eval_report or eval_report.get("policy_version") != manifest["policy_version"] \
            or eval_report.get("model_versions") != manifest["model_versions"]:
        raise ReleaseRefused("no_eval_report")
    if eval_report.get("failing_categories"):
        raise ReleaseRefused("eval_failing", ",".join(eval_report["failing_categories"]))
    dest = out_root / "released" / batch_id
    dest.mkdir(parents=True, exist_ok=True)
    for f in manifest["files"]:
        target = dest / f["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged / f["path"], target)
    return sorted({f["call_id"] for f in manifest["files"]})
