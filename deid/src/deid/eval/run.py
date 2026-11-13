"""EVAL-SYNTHETIC runner: generate a gold set, run the pipeline on it, score it, write a report.

    python -m deid.eval.run --per-variant 24 --seed 20261113 --out eval-out/run1

The report states what it binds to. It is never real-world recall.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path

from .. import __version__, netguard
from ..asr import FasterWhisperTranscriber
from ..lexicon import Lexicon
from ..pipeline import CallAudio, Deps, OutputDirs, process_call
from ..policy import load_policy
from ..redact import plan_spans
from ..textnorm import is_placeholder
from .synth import VOICE_LICENCES, VOICES, generate, gold_to_json

PROFILES = {"es_ES": "ES-GENERIC-es-S2", "es_MX": "MX-GENERIC-es-S2", "en_US": "US-GENERIC-en-S2"}
# Plan 001 §11.3. Strict recall on synthetic audio. CARD appears only in calls that must drop.
TARGETS = {"CARD": 1.0, "NATIONAL_ID": 0.99, "IBAN": 0.99, "ACCOUNT": 0.99, "PHONE": 0.99, "EMAIL": 0.98,
           "REFERENCE": 0.98, "BRAND": 0.99, "NAME": 0.95, "ADDRESS": 0.95, "DOB": 0.95, "SPELLED": 0.98}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def _covered(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    s, e = span
    for a, b in spans:
        if a <= s and b >= e:
            return True
    return False


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def score_call(gold: dict, log: dict, transcript: dict | None, pads: tuple[int, int]) -> dict:
    """Per gold entity: audio covered, transcript clean. Only meaningful for staged calls."""
    dur = gold["duration_ms"] + 1000
    ent_spans = [(r["start_ms"], r["end_ms"]) for r in log["removals"] if r["detector"] != "untranscribed"]
    out = []
    redacted = {}
    for ch in ("agent", "customer"):
        unc = [(r["start_ms"], r["end_ms"]) for r in log["removals"]
               if r["detector"] == "untranscribed" and r["channel"] == ch]
        redacted[ch] = plan_spans(ent_spans + unc, dur, *pads)
        redacted[ch + "_entities_only"] = plan_spans(ent_spans, dur, *pads)
    for g in gold["entities"]:
        span = (g["start_ms"], g["end_ms"])
        audio_ok = _covered(span, redacted[g["channel"]])
        leaked = []
        if transcript:
            for w in transcript["channels"][g["channel"]]:
                if is_placeholder(w["t"]):
                    continue
                wd = max(1, w["e"] - w["s"])
                if _overlap((w["s"], w["e"]), span) / wd > 0.5:
                    leaked.append(w["t"])
        # boundary error: how far the merged unpadded detections on this channel fall short of the gold speech span
        same = sorted((r["start_ms"], r["end_ms"]) for r in log["removals"]
                      if r["channel"] == g["channel"] and r["detector"] != "untranscribed")
        merged = plan_spans(same, dur, 0, 0)
        hit = [m for m in merged if _overlap(m, span) > 0]
        b_err = None
        if hit:
            b_err = {"start_short_ms": min(m[0] for m in hit) - span[0], "end_short_ms": span[1] - max(m[1] for m in hit)}
        out.append({"category": g["category"], "channel": g["channel"], "audio_ok": audio_ok,
                    "transcript_ok": not leaked, "n_leaked_tokens": len(leaked), "boundary": b_err})
    # precision: entity-redacted ms that overlap a gold entity on that channel
    red_ms = hit_ms = 0
    for ch in ("agent", "customer"):
        gspans = [(g["start_ms"], g["end_ms"]) for g in gold["entities"] if g["channel"] == ch]
        for a, b in redacted[ch + "_entities_only"]:
            red_ms += b - a
            hit_ms += sum(_overlap((a, b), gs) for gs in gspans)
    total_red = sum(b - a for ch in ("agent", "customer") for a, b in redacted[ch])
    return {"entities": out, "redacted_ms": red_ms, "hit_ms": hit_ms, "total_redacted_ms": total_red,
            "audio_ms": 2 * gold["duration_ms"]}


def git_commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                           cwd=Path(__file__).resolve().parent)
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], capture_output=True, text=True,
                               cwd=Path(__file__).resolve().parents[3]).stdout.strip()
        return r.stdout.strip() + ("+dirty" if dirty else "")
    except OSError:
        return "unknown"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-variant", type=int, default=24)
    ap.add_argument("--variants", default="es_ES,es_MX,en_US")
    ap.add_argument("--seed", type=int, default=20261113)
    ap.add_argument("--models", default="models")
    ap.add_argument("--asr", default="faster-whisper-small")
    ap.add_argument("--compute-type", default="int8")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    a.commit = git_commit()  # stamped at start: edits made while the run proceeds must not re-stamp it
    out = Path(a.out)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    variants = a.variants.split(",")
    policy = load_policy()
    models = Path(a.models)
    gen = generate(models / "tts", variants, a.per_variant, a.seed)  # TTS loads before the guard; no network
    netguard.install()
    tr = FasterWhisperTranscriber(models / "asr" / a.asr, device=a.device, compute_type=a.compute_type)
    key = os.urandom(32)  # eval only; never reused
    rows = []
    audio_s = wall_s = 0.0
    for gc, ag, cu in gen:
        prof = policy.profile(PROFILES[gc.variant])
        dirs = OutputDirs(out / "staged" / gc.variant, out / "logs", batch_id=gc.variant)
        t0 = time.time()
        log = process_call(CallAudio(ag, cu, 8000, ag.tobytes() + cu.tobytes()), prof, policy,
                           Deps(tr, Lexicon.empty(), key), dirs)
        wall_s += time.time() - t0
        audio_s += gc.duration_ms / 1000
        gold = json.loads(gold_to_json(gc))
        tpath = dirs.staged / f"{log.call_id}.json"
        transcript = json.loads(tpath.read_text()) if tpath.exists() else None
        sc = score_call(gold, log.to_dict(), transcript, (prof.pad_before_ms, prof.pad_after_ms))
        row = {"call_key": gc.call_key, "variant": gc.variant, "expected_drop": gc.expected_drop,
               "decision": log.decision.value, "drop_reason": log.drop_reason.value if log.drop_reason else None,
               "error_class": log.error_class, "hard_cases": gc.hard_cases, **sc}
        rows.append(row)
        with open(out / "gold.jsonl", "a") as f:
            f.write(gold_to_json(gc) + "\n")
        with open(out / "rows.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")
        print(f"{gc.call_key} expected={gc.expected_drop} got={row['decision']}/{row['drop_reason']} "
              f"err={row['error_class']}", flush=True)
    report = summarise(rows, a, policy, tr.model_digest, audio_s, wall_s)
    (out / "report.json").write_text(json.dumps(report, indent=1))
    (out / "report.md").write_text(render_md(report))
    print(render_md(report))


def summarise(rows, a, policy, asr_digest, audio_s, wall_s) -> dict:
    cats = defaultdict(lambda: [0, 0, 0, 0])  # n, strict_ok, audio_ok, transcript_ok
    by_hard = defaultdict(lambda: [0, 0])
    conf = defaultdict(Counter)
    red = hit = total_red = audio_ms = 0
    staged = leaky = 0
    errors = Counter()
    for r in rows:
        exp = r["expected_drop"] or "keep"
        got = "keep" if r["decision"] == "released_to_staging" else r["drop_reason"]
        conf[(r["variant"], exp)][got] += 1
        if r["error_class"]:
            errors[r["error_class"]] += 1
        if r["decision"] != "released_to_staging":
            continue
        staged += 1
        any_miss = False
        red += r["redacted_ms"]
        hit += r["hit_ms"]
        total_red += r["total_redacted_ms"]
        audio_ms += r["audio_ms"]
        for e in r["entities"]:
            ok = e["audio_ok"] and e["transcript_ok"]
            c = cats[(r["variant"], e["category"])]
            c[0] += 1
            c[1] += ok
            c[2] += e["audio_ok"]
            c[3] += e["transcript_ok"]
            any_miss |= not ok
        for h in r["hard_cases"]:
            by_hard[h][0] += 1
            by_hard[h][1] += not any(not (e["audio_ok"] and e["transcript_ok"]) for e in r["entities"])
        leaky += any_miss
    starts = sorted(e["boundary"]["start_short_ms"] for r in rows if r["decision"] == "released_to_staging"
                    for e in r["entities"] if e.get("boundary"))
    ends = sorted(e["boundary"]["end_short_ms"] for r in rows if r["decision"] == "released_to_staging"
                  for e in r["entities"] if e.get("boundary"))

    def q(xs, p):
        return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None
    boundary = {"n": len(starts), "note": "positive = the detected span starts late / ends early vs gold speech",
                "start_short_ms": {"p50": q(starts, .5), "p90": q(starts, .9), "p99": q(starts, .99),
                                   "max": starts[-1] if starts else None},
                "end_short_ms": {"p50": q(ends, .5), "p90": q(ends, .9), "p99": q(ends, .99),
                                 "max": ends[-1] if ends else None}}
    per_cat = []
    pooled = defaultdict(lambda: [0, 0])
    for (v, c), (n, ok, aok, tok) in sorted(cats.items()):
        lo, hi = wilson(ok, n)
        per_cat.append({"variant": v, "category": c, "n": n, "strict_recall": ok / n if n else None,
                        "ci95": [round(lo, 3), round(hi, 3)], "audio_recall": aok / n, "transcript_recall": tok / n,
                        "target": TARGETS.get(c)})
        pooled[c][0] += n
        pooled[c][1] += ok
    failing = sorted(c for c, (n, ok) in pooled.items() if c in TARGETS and n and ok / n < TARGETS[c])
    missed_drops = sum(cnt for (v, exp), cn in conf.items() if exp != "keep" for got, cnt in cn.items()
                       if got == "keep")
    if missed_drops:
        failing.append("EXCLUSION")
    return {
        "evidence_class": "EVAL-SYNTHETIC",
        "binds_to": {
            "generator_commit": a.commit, "seed": a.seed, "per_variant": a.per_variant,
            "variants": a.variants.split(","), "voices": {v: list(VOICES[v]) for v in a.variants.split(",")},
            "voice_licences": VOICE_LICENCES, "asr_model": a.asr, "asr_compute_type": a.compute_type,
            "asr_device": a.device, "pipeline_version": __version__, "policy_digest": policy.digest,
            "operator_lexicon": "absent (brand and agent-name recall measured without one)",
        },
        "policy_version": policy.version,
        "model_versions": {"asr": asr_digest},
        "failing_categories": failing,
        "missed_drops": missed_drops,
        "calls": len(rows), "staged_calls": staged,
        "leak_rate_staged_calls": (leaky / staged) if staged else None, "leaky_staged_calls": leaky,
        "per_category": per_cat,
        "pooled": {c: {"n": n, "strict_recall": ok / n, "ci95": [round(x, 3) for x in wilson(ok, n)],
                       "target": TARGETS.get(c)} for c, (n, ok) in sorted(pooled.items())},
        "hard_cases_clean_call_rate": {h: {"calls": n, "clean": k} for h, (n, k) in sorted(by_hard.items())},
        "boundary_error": boundary,
        "audio_precision": (hit / red) if red else None,
        "share_of_audio_redacted": (total_red / audio_ms) if audio_ms else None,
        "drop_confusion": {f"{v}|{exp}": dict(cn) for (v, exp), cn in sorted(conf.items())},
        "error_classes": dict(errors),
        "throughput": {"audio_seconds": round(audio_s, 1), "wall_seconds": round(wall_s, 1),
                       "real_time_factor": round(wall_s / audio_s, 3) if audio_s else None,
                       "hardware": f"CPU only: {platform.processor() or platform.machine()}, {os.cpu_count()} cores. "
                                   "NOT a GPU figure.",
                       "note": "audio_seconds counts call duration once; both channels are transcribed."},
    }


def render_md(r: dict) -> str:
    b = r["binds_to"]
    L = [f"# deid evaluation report ({r['evidence_class']})", "",
         "**Synthetic TTS audio, not real telephony. This is not real-world recall and must not be quoted as such.**",
         "It is an upper bound on what the pipeline has shown on audio we generated.", "",
         "## Binds to", ""]
    for k, v in b.items():
        L.append(f"- {k}: `{json.dumps(v, ensure_ascii=False)}`")
    L += [f"- policy_version: `{r['policy_version']}`", f"- asr digest: `{r['model_versions']['asr']}`", "",
          "## Headline", "",
          f"- Calls: {r['calls']}; staged (not dropped): {r['staged_calls']}",
          f"- **Missed drops (excluded calls staged): {r['missed_drops']}**",
          f"- Leak rate (staged calls with any surviving gold identifier): "
          f"{r['leaky_staged_calls']}/{r['staged_calls']}"
          + (f" = {r['leak_rate_staged_calls']:.1%}" if r['leak_rate_staged_calls'] is not None else ""),
          f"- Failing categories vs plan targets: {', '.join(r['failing_categories']) or 'none'}",
          f"- Audio precision (entity-redacted ms on a gold identifier): "
          + (f"{r['audio_precision']:.1%}" if r['audio_precision'] is not None else "n/a"),
          f"- Share of all audio filled (entities + untranscribed speech): "
          + (f"{r['share_of_audio_redacted']:.1%}" if r['share_of_audio_redacted'] is not None else "n/a"),
          f"- Errors (calls dropped as stage_error): {r['error_classes'] or 'none'}", "",
          "## Strict recall, pooled across variants", "",
          "Strict = 100% of the identifier's audio span filled AND no transcript token over it left in clear.", "",
          "| Category | n | strict recall | 95% CI | target |", "|---|---|---|---|---|"]
    for c, p in r["pooled"].items():
        L.append(f"| {c} | {p['n']} | {p['strict_recall']:.3f} | {p['ci95'][0]:.3f}-{p['ci95'][1]:.3f} | "
                 f"{p['target']} |")
    L += ["", "## Per variant", "", "| Variant | Category | n | strict | audio | transcript | 95% CI (strict) |",
          "|---|---|---|---|---|---|---|"]
    for p in r["per_category"]:
        L.append(f"| {p['variant']} | {p['category']} | {p['n']} | {p['strict_recall']:.3f} | "
                 f"{p['audio_recall']:.3f} | {p['transcript_recall']:.3f} | {p['ci95'][0]:.3f}-{p['ci95'][1]:.3f} |")
    L += ["", "## Drop classifier: confusion (expected -> got)", "", "Missed drops are listed first in each row.", "",
          "| Variant / expected | got |", "|---|---|"]
    for k, v in r["drop_confusion"].items():
        L.append(f"| {k} | {json.dumps(v)} |")
    L += ["", "## Hard cases: calls with every gold identifier removed", "", "| Hard case | calls | clean |",
          "|---|---|---|"]
    for h, v in r["hard_cases_clean_call_rate"].items():
        L.append(f"| {h} | {v['calls']} | {v['clean']} |")
    be = r["boundary_error"]
    L += ["", "## Boundary error of detected spans (before padding)", "", f"- n = {be['n']}; {be['note']}",
          f"- start: {be['start_short_ms']}", f"- end: {be['end_short_ms']}"]
    t = r["throughput"]
    L += ["", "## Throughput", "", f"- {t['hardware']}",
          f"- {t['audio_seconds']} s of calls in {t['wall_seconds']} s wall: real-time factor {t['real_time_factor']}",
          f"- {t['note']}", "", "## What this does not show", "",
          "- Real callers: accents, noise, codecs, emotional speech, names outside our lists. See plan §11.4-11.5.",
          "- Formats our generator does not produce.",
          "- Voice anonymisation (not built; profiles that require it drop every call).",
          "- Recall with an operator lexicon (none used here; the BPO's lexicon should raise BRAND and NAME).",
          "- GPU throughput."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
