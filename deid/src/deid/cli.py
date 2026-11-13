"""deid command line. Every command runs offline; `run` installs the network guard before reading any input.

  deid run            --input DIR --batch-meta FILE --out DIR --models DIR --hmac-key-file FILE --batch-id ID
                      [--lexicon FILE] [--device cpu|cuda] [--compute-type int8|float16]
  deid policy-lock    --version X.Y.Z
  deid verify-manifest --out DIR --batch-id ID
  deid approve        --out DIR --batch-id ID --reviewer CODE (--approve | --reject) --reason CODE
  deid release        --out DIR --batch-id ID --eval-report FILE
  deid review         --out DIR --work DIR --batch-id ID [--sample 50] [--seed N] [--port 8765]
  deid montu-view     --out DIR [ls | cat PATH]

Output layout: out/staged/<batch>/  (BPO only until released)   out/logs/  (Montu-readable)
               out/released/<batch>/  (Montu-readable)          work/ (BPO only: notes, never copied to out/)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections import Counter
from pathlib import Path

AUDIO_EXT = {".wav", ".opus", ".ogg", ".mp3", ".flac"}


def _calls(input_dir: Path, pairing: str | None) -> list[list[Path]]:
    files = sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXT)
    if not pairing:
        return [[p] for p in files]
    a_pat, c_pat = pairing.split("|")

    def rx(pat: str) -> re.Pattern:
        return re.compile("^" + re.escape(pat).replace(re.escape("{id}"), "(?P<id>.+)") + "$")
    ra, rc = rx(a_pat), rx(c_pat)
    by_id: dict[str, dict[str, Path]] = {}
    for p in files:
        for role, r in (("agent", ra), ("customer", rc)):
            m = r.match(p.name)
            if m:
                by_id.setdefault(m.group("id"), {})[role] = p
    out = []
    for k in sorted(by_id):
        d = by_id[k]
        out.append([d["agent"], d["customer"]] if len(d) == 2 else list(d.values()))  # unpaired => unreadable
    return out


def cmd_run(a) -> int:
    from . import netguard
    netguard.install()
    from .asr import FasterWhisperTranscriber
    from .audio import UnreadableAudio, decode
    from .lexicon import load_lexicon
    from .manifest import build_manifest
    from .metadata import MetadataRejected, parse_batch_metadata
    from .pipeline import CallAudio, Deps, OutputDirs, log_drop, process_call
    from .policy import load_policy
    from .types import DropReason

    policy = load_policy()
    try:
        meta = parse_batch_metadata(tomllib.loads(Path(a.batch_meta).read_text()), policy)
    except MetadataRejected as e:
        print(f"batch rejected: {e.reason}", file=sys.stderr)
        return 2
    profile = policy.profile(meta.profile_code)
    lexicon = load_lexicon(Path(a.lexicon) if a.lexicon else None)
    if profile.brand_lexicon == "required" and not lexicon.present:
        print("batch rejected: profile requires a private lexicon and none was given", file=sys.stderr)
        return 2
    key = Path(a.hmac_key_file).read_bytes()
    if len(key) < 32:
        print("hmac key must be at least 32 bytes", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", a.batch_id):
        print("batch id: letters, digits, _ and - only", file=sys.stderr)
        return 2
    out = Path(a.out)
    dirs = OutputDirs(out / "staged" / a.batch_id, out / "logs", batch_id=a.batch_id)
    tr = FasterWhisperTranscriber(Path(a.models) / "asr" / a.asr, device=a.device, compute_type=a.compute_type)
    deps = Deps(tr, lexicon, key)
    counts: Counter = Counter()
    for files in _calls(Path(a.input), meta.pairing):
        src = b"".join(p.read_bytes() for p in files)
        try:
            if len(files) == 1:
                x, sr = decode(files[0], 8000)
                if x.shape[1] != 2:
                    raise UnreadableAudio("not two channels")
                ag, cu = x[:, meta.channel_map["agent"]], x[:, meta.channel_map["customer"]]
            elif len(files) == 2:
                (xa, sr), (xc, _) = decode(files[0], 8000), decode(files[1], 8000)
                if xa.shape[1] != 1 or xc.shape[1] != 1:
                    raise UnreadableAudio("dual-mono files must be mono")
                ag, cu = xa[:, 0], xc[:, 0]
            else:
                raise UnreadableAudio("unpaired")
        except Exception:  # decoding failures drop the call; nothing about the file is logged but its keyed hash
            log = log_drop(src, profile, policy, deps, dirs, DropReason.UNREADABLE_AUDIO)
        else:
            log = process_call(CallAudio(ag, cu, sr, src), profile, policy, deps, dirs)
        counts[log.drop_reason.value if log.drop_reason else "staged"] += 1
    dirs.staged.mkdir(parents=True, exist_ok=True)
    m = build_manifest(dirs.staged, a.batch_id, policy.version, {"asr": tr.model_digest})
    m["profile_code"] = profile.code
    m["uncited_rules_in_jurisdiction"] = len(profile.todo_rules)
    m["operator_lexicon"] = "present" if lexicon.present else "absent"
    m["counts"] = dict(counts)
    (out / "logs" / f"{a.batch_id}.manifest.json").write_text(json.dumps(m, indent=1, sort_keys=True))
    print(json.dumps({"batch_id": a.batch_id, "counts": dict(counts), "policy_version": policy.version,
                      "uncited_rules": len(profile.todo_rules), "operator_lexicon": m["operator_lexicon"]}))
    return 0


def cmd_policy_lock(a) -> int:
    from .policy import DEFAULT_POLICY_DIR, write_lock
    write_lock(Path(a.policy_dir) if a.policy_dir else DEFAULT_POLICY_DIR, a.version)
    print(f"locked {a.version}")
    return 0


def cmd_verify(a) -> int:
    from .manifest import verify_manifest
    out = Path(a.out)
    m = json.loads((out / "logs" / f"{a.batch_id}.manifest.json").read_text())
    diff = verify_manifest(out / "staged" / a.batch_id, m)
    if diff:
        print("MISMATCH: " + ", ".join(diff))
        return 1
    print(f"verified {len(m['files'])} files")
    return 0


def cmd_approve(a) -> int:
    from .manifest import manifest_digest
    from .release import record_approval
    out = Path(a.out)
    m = json.loads((out / "logs" / f"{a.batch_id}.manifest.json").read_text())
    record_approval(out, a.batch_id, manifest_digest(m), a.reviewer, a.approve, a.reason)
    print("recorded")
    return 0


def cmd_release(a) -> int:
    from .release import ReleaseRefused, release
    report = json.loads(Path(a.eval_report).read_text()) if a.eval_report else None
    try:
        ids = release(Path(a.out), a.batch_id, report)
    except ReleaseRefused as e:
        print(f"release refused: {e.reason}", file=sys.stderr)
        return 1
    print(f"released {len(ids)} calls")
    return 0


def cmd_review(a) -> int:
    from . import netguard
    netguard.install()  # the review server listens on 127.0.0.1; it never connects out
    from .review_app import serve
    serve(Path(a.out), Path(a.work), a.batch_id, a.sample, a.seed, a.port)
    return 0


def cmd_montu_view(a) -> int:
    from .roles import MontuView
    v = MontuView(Path(a.out))
    if a.action == "ls":
        print("\n".join(v.list()))
    else:
        sys.stdout.buffer.write(v.read(a.path))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="deid")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    for k in ("input", "batch-meta", "out", "models", "hmac-key-file", "batch-id"):
        r.add_argument(f"--{k}", required=True)
    r.add_argument("--lexicon")
    r.add_argument("--asr", default="faster-whisper-small")
    r.add_argument("--device", default="auto")
    r.add_argument("--compute-type", default="default")
    r.set_defaults(fn=cmd_run)
    p = sub.add_parser("policy-lock")
    p.add_argument("--version", required=True)
    p.add_argument("--policy-dir")
    p.set_defaults(fn=cmd_policy_lock)
    for name, fn in (("verify-manifest", cmd_verify),):
        s = sub.add_parser(name)
        s.add_argument("--out", required=True)
        s.add_argument("--batch-id", required=True)
        s.set_defaults(fn=fn)
    s = sub.add_parser("approve")
    s.add_argument("--out", required=True)
    s.add_argument("--batch-id", required=True)
    s.add_argument("--reviewer", required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--approve", action="store_true")
    g.add_argument("--reject", action="store_true")
    s.add_argument("--reason", required=True)
    s.set_defaults(fn=cmd_approve)
    s = sub.add_parser("release")
    s.add_argument("--out", required=True)
    s.add_argument("--batch-id", required=True)
    s.add_argument("--eval-report")
    s.set_defaults(fn=cmd_release)
    s = sub.add_parser("review")
    s.add_argument("--out", required=True)
    s.add_argument("--work", required=True)
    s.add_argument("--batch-id", required=True)
    s.add_argument("--sample", type=int, default=50)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(fn=cmd_review)
    s = sub.add_parser("montu-view")
    s.add_argument("--out", required=True)
    s.add_argument("action", choices=["ls", "cat"])
    s.add_argument("path", nargs="?")
    s.set_defaults(fn=cmd_montu_view)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
