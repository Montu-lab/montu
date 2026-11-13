"""Policies are versioned data under policies/. This module loads and checks them; it holds no rules."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class PolicyError(Exception):
    """reason is one of: uncited_rule, unknown_trigger, lock_mismatch, lock_missing,
    version_exists, unknown_profile, bad_profile."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class Rule:
    id: str
    trigger: str
    action: str
    citation: str | None
    verified: bool
    status: str  # "active" | "todo"
    citation_gap: str | None


@dataclass(frozen=True)
class Profile:
    code: str
    jurisdiction: str
    sector: str
    languages: tuple[str, ...]
    strictness: str
    voice_anon: str
    fill: str
    digit_catch_all: int
    pad_before_ms: int
    pad_after_ms: int
    brand_lexicon: str
    rules: tuple[Rule, ...]  # active rules only
    todo_rules: tuple[Rule, ...]
    lexicon_dir: Path = field(compare=False, default=Path("."))


@dataclass(frozen=True)
class PolicySet:
    version: str
    digest: str  # sha256 over all policy files, in path order
    profiles: dict[str, Profile]

    def profile(self, code: str) -> Profile:
        raise NotImplementedError


DEFAULT_POLICY_DIR = Path(__file__).resolve().parents[2] / "policies"


def load_policy(policy_dir: Path = DEFAULT_POLICY_DIR) -> PolicySet:
    raise NotImplementedError


def write_lock(policy_dir: Path, version: str) -> None:
    """Record the digest of the current files under `version`. Refuses (version_exists) to rewrite
    an entry that already exists: a content change needs a new version."""
    raise NotImplementedError
