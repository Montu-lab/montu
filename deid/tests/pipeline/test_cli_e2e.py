"""PIPELINE. The CLI end to end on generated stereo WAV files with the real local ASR model.
Says the parts connect and the gates hold on real files. Says nothing about recall."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
pytestmark = pytest.mark.pipeline

if not (MODELS / "asr" / "faster-whisper-small" / "model.bin").exists():
    pytest.skip("NOT RUN: models/asr/faster-whisper-small missing (scripts/fetch_models.py)", allow_module_level=True)


def deid(*args):
    return subprocess.run([sys.executable, "-m", "deid.cli", *map(str, args)], capture_output=True, text=True,
                          cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"})


@pytest.fixture(scope="module")
def batch(tmp_path_factory):
    from deid.audio import write_wav
    from deid.eval.synth import generate
    d = tmp_path_factory.mktemp("e2e")
    inp = d / "in"
    inp.mkdir()
    gen = generate(MODELS / "tts", ["es_ES"], 2, 4242, drop_share=0.0)
    for i, (gc, a, c) in enumerate(gen):
        # filename deliberately carries a phone-number-like string: it must never reach a log
        write_wav(inp / f"call_612345678_{i}.wav", [a, c], 8000)
    (inp / "broken_699111222.wav").write_bytes(b"RIFF not audio")
    (d / "batch.toml").write_text('profile_code = "ES-GENERIC-es-S2"\nchannel_map = {agent = 0, customer = 1}\n')
    (d / "key").write_bytes(b"x" * 32)
    r = deid("run", "--input", inp, "--batch-meta", d / "batch.toml", "--out", d / "out", "--models", MODELS,
             "--hmac-key-file", d / "key", "--batch-id", "B1", "--device", "cpu", "--compute-type", "int8")
    assert r.returncode == 0, r.stderr[-2000:]
    return d, json.loads(r.stdout.strip().splitlines()[-1])


def test_run_counts_and_unreadable_drop(batch):
    d, summary = batch
    assert sum(summary["counts"].values()) == 3
    assert summary["counts"].get("unreadable_audio") == 1


def test_logs_carry_no_filename_digits(batch):
    d, _ = batch
    for f in (d / "out" / "logs").iterdir():
        text = f.read_text()
        assert "612345678" not in text and "699111222" not in text and "call_612" not in text and "broken" not in text


def test_manifest_verifies_then_release_gates(batch):
    d, _ = batch
    out = d / "out"
    assert deid("verify-manifest", "--out", out, "--batch-id", "B1").returncode == 0
    m = json.loads((out / "logs" / "B1.manifest.json").read_text())
    report = d / "eval.json"
    report.write_text(json.dumps({"policy_version": m["policy_version"], "model_versions": m["model_versions"],
                                  "failing_categories": []}))
    r = deid("release", "--out", out, "--batch-id", "B1", "--eval-report", report)
    assert r.returncode == 1 and "no_approval" in r.stderr
    assert deid("approve", "--out", out, "--batch-id", "B1", "--reviewer", "rev-1", "--approve",
                "--reason", "ok").returncode == 0
    r = deid("release", "--out", out, "--batch-id", "B1", "--eval-report", report)
    assert r.returncode == 0, r.stderr
    assert sorted(p.suffix for p in (out / "released" / "B1").iterdir()) == [".json", ".json", ".wav", ".wav"] \
        or len(list((out / "released" / "B1").iterdir())) == 2 * summary_staged(out)


def summary_staged(out):
    return sum(1 for line in (out / "logs" / "B1.calls.jsonl").read_text().splitlines()
               if json.loads(line)["decision"] == "released_to_staging")


def test_client_name_in_metadata_rejects_batch(batch, tmp_path):
    d, _ = batch
    bad = tmp_path / "bad.toml"
    bad.write_text('profile_code = "ES-GENERIC-es-S2"\nchannel_map = {agent = 0, customer = 1}\n'
                   'client_name = "Movistela"\n')
    r = deid("run", "--input", d / "in", "--batch-meta", bad, "--out", tmp_path / "o", "--models", MODELS,
             "--hmac-key-file", d / "key", "--batch-id", "B2")
    assert r.returncode == 2 and "unknown_key" in r.stderr and "Movistela" not in r.stderr
    assert not (tmp_path / "o").exists()


def test_montu_view_cannot_read_staged(batch):
    d, _ = batch
    r = deid("montu-view", "--out", d / "out", "ls")
    assert r.returncode == 0 and all(x.startswith(("logs/", "released/")) for x in r.stdout.split())
