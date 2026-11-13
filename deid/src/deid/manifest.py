"""Batch manifest: SHA-256 of every staged output file."""
from __future__ import annotations

from pathlib import Path


def build_manifest(staged_dir: Path, batch_id: str, policy_version: str,
                   model_versions: dict) -> dict:
    raise NotImplementedError


def manifest_digest(manifest: dict) -> str:
    raise NotImplementedError


def verify_manifest(staged_dir: Path, manifest: dict) -> list[str]:
    """Returns the relative paths that differ (changed, missing or extra). Empty means verified."""
    raise NotImplementedError
