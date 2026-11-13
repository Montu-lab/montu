"""Batch manifest: SHA-256 of every staged output file."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _files(staged_dir: Path) -> list[Path]:
    return sorted(p for p in Path(staged_dir).rglob("*") if p.is_file())


def build_manifest(staged_dir: Path, batch_id: str, policy_version: str, model_versions: dict) -> dict:
    staged_dir = Path(staged_dir)
    return {
        "batch_id": batch_id,
        "policy_version": policy_version,
        "model_versions": dict(sorted(model_versions.items())),
        "files": [{"path": str(p.relative_to(staged_dir)), "sha256": _sha(p), "size": p.stat().st_size,
                   "call_id": p.name.split(".")[0]} for p in _files(staged_dir)],
    }


def manifest_digest(manifest: dict) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_manifest(staged_dir: Path, manifest: dict) -> list[str]:
    """Returns the relative paths that differ (changed, missing or extra). Empty means verified."""
    staged_dir = Path(staged_dir)
    want = {f["path"]: f["sha256"] for f in manifest["files"]}
    have = {str(p.relative_to(staged_dir)): _sha(p) for p in _files(staged_dir)}
    return sorted(p for p in set(want) | set(have) if want.get(p) != have.get(p))
