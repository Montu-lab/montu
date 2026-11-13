"""Policies are versioned data under policies/. This module loads and checks them; it holds no rules."""
from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .types import TRIGGER_TO_REASON

LOCK_NAME = "POLICY_LOCK.toml"
PROFILE_CODE = re.compile(r"^[A-Z]{2}-[A-Z]+-[a-z]{2}(\+[a-z]{2})*-S[1-3]$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
# The brief drops these by default. A profile whose jurisdiction lacks an active rule for any of them is refused,
# so a missing rule cannot silently mean "keep".
REQUIRED_TRIGGERS = frozenset(TRIGGER_TO_REASON)
LEXICON_TRIGGERS = ("special_category", "minor", "vulnerable", "pci_cue")


class PolicyError(Exception):
    """reason is one of: uncited_rule, unknown_trigger, lock_mismatch, lock_missing, version_exists,
    version_mismatch, unknown_profile, bad_profile, bad_rule."""

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
    lexicons: dict = field(compare=False, default_factory=dict)  # lang -> trigger -> tuple[phrase]


@dataclass(frozen=True)
class PolicySet:
    version: str
    digest: str  # sha256 over all policy files, in path order
    profiles: dict[str, Profile]

    def profile(self, code: str) -> Profile:
        if code not in self.profiles:
            raise PolicyError("unknown_profile")
        return self.profiles[code]


DEFAULT_POLICY_DIR = Path(__file__).resolve().parents[2] / "policies"


def policy_digest(policy_dir: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in policy_dir.rglob("*") if p.is_file() and p.name != LOCK_NAME):
        h.update(str(f.relative_to(policy_dir)).encode() + b"\0")
        h.update(hashlib.sha256(f.read_bytes()).hexdigest().encode() + b"\n")
    return h.hexdigest()


def _read_lock(policy_dir: Path) -> dict:
    p = policy_dir / LOCK_NAME
    return tomllib.loads(p.read_text()) if p.exists() else {}


def _rules(path: Path) -> list[Rule]:
    data = tomllib.loads(path.read_text())
    out = []
    for r in data.get("rules", []):
        rid = r.get("id")
        if not rid or r.get("action") != "drop":
            raise PolicyError("bad_rule", str(path.name))
        if r.get("trigger") not in TRIGGER_TO_REASON:
            raise PolicyError("unknown_trigger", rid)
        status = r.get("status", "active")
        if status == "todo":
            if not r.get("citation_gap"):
                raise PolicyError("uncited_rule", rid)
        elif status == "active":
            if not r.get("citation") or not isinstance(r.get("verified"), bool):
                raise PolicyError("uncited_rule", rid)
        else:
            raise PolicyError("bad_rule", rid)
        out.append(Rule(rid, r["trigger"], r["action"], r.get("citation"), bool(r.get("verified", False)),
                        status, r.get("citation_gap")))
    return out


def _lexicon(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    lines = (ln.split("#", 1)[0].strip() for ln in path.read_text().splitlines())
    return tuple(ln for ln in lines if ln)


def load_policy(policy_dir: Path = DEFAULT_POLICY_DIR) -> PolicySet:
    policy_dir = Path(policy_dir)
    meta = tomllib.loads((policy_dir / "policy.toml").read_text())
    version = meta.get("version", "")
    if not SEMVER.match(version):
        raise PolicyError("bad_rule", "policy version")
    jur_rules = {p.stem: _rules(p) for p in sorted((policy_dir / "jurisdictions").glob("*.toml"))}
    raw_profiles = tomllib.loads((policy_dir / "profiles.toml").read_text()).get("profiles", {})
    profiles = {}
    for code, p in raw_profiles.items():
        if not PROFILE_CODE.match(code) or p.get("jurisdiction") not in jur_rules:
            raise PolicyError("bad_profile", code)
        rules = jur_rules[p["jurisdiction"]]
        active = tuple(r for r in rules if r.status == "active")
        missing = REQUIRED_TRIGGERS - {r.trigger for r in active}
        if missing:
            raise PolicyError("bad_profile", f"{code} has no active rule for {sorted(missing)}")
        if p.get("voice_anon") not in ("off", "weak_ok", "required") or p.get("fill") not in ("silence", "tone") \
                or p.get("brand_lexicon") not in ("optional", "required"):
            raise PolicyError("bad_profile", code)
        langs = tuple(p["languages"])
        lex = {lang: {t: _lexicon(policy_dir / "lexicons" / lang / f"{t}.txt") for t in LEXICON_TRIGGERS}
               for lang in langs}
        for lang in langs:
            if not (policy_dir / "lexicons" / lang).is_dir():
                raise PolicyError("bad_profile", f"{code}: no lexicons for {lang}")
        profiles[code] = Profile(
            code=code, jurisdiction=p["jurisdiction"], sector=p["sector"], languages=langs,
            strictness=p["strictness"], voice_anon=p["voice_anon"], fill=p["fill"],
            digit_catch_all=int(p["digit_catch_all"]), pad_before_ms=int(p["pad_before_ms"]),
            pad_after_ms=int(p["pad_after_ms"]), brand_lexicon=p["brand_lexicon"], rules=active,
            todo_rules=tuple(r for r in rules if r.status == "todo"), lexicon_dir=policy_dir / "lexicons",
            lexicons=lex)
    # Content is validated first, then the lock: a content change without a new version is refused.
    digest = policy_digest(policy_dir)
    lock = _read_lock(policy_dir)
    if not lock:
        raise PolicyError("lock_missing")
    entry = lock.get("versions", {}).get(version)
    if not entry or entry.get("digest") != digest:
        raise PolicyError("lock_mismatch", f"policy files do not match the lock for version {version}")
    return PolicySet(version, digest, profiles)


def write_lock(policy_dir: Path, version: str) -> None:
    """Record the digest of the current files under `version`. Refuses (version_exists) to rewrite
    an entry that already exists: a content change needs a new version."""
    policy_dir = Path(policy_dir)
    meta = tomllib.loads((policy_dir / "policy.toml").read_text())
    digest = policy_digest(policy_dir)
    lock = _read_lock(policy_dir)
    versions = lock.get("versions", {})
    if version in versions:
        if versions[version]["digest"] == digest:
            return
        raise PolicyError("version_exists", version)
    if meta.get("version") != version:
        raise PolicyError("version_mismatch", "policy.toml version differs from the version being locked")
    versions[version] = {"digest": digest}
    lines = ["# Written by `deid policy-lock`. One entry per policy version; entries are never rewritten.", ""]
    for v in versions:
        lines += [f'[versions."{v}"]', f'digest = "{versions[v]["digest"]}"', ""]
    (policy_dir / LOCK_NAME).write_text("\n".join(lines))
