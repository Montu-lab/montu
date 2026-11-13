"""UNIT (orchestration with a fake transcriber). Exercises drop paths, the leak scan and the log.
Says nothing about real ASR, real audio or recall."""
import json
import re

import numpy as np
import pytest

from deid.asr import Transcript
from deid.calllog import ModelSlot
from deid.lexicon import Lexicon
from deid.pipeline import CallAudio, Deps, OutputDirs, process_call
from deid.types import Channel

from conftest import mkwords

SR = 8000
KEY = b"k" * 32


class FakeTranscriber:
    model_digest = "c" * 64

    def __init__(self, agent, customer, lang="es", prob=0.99, raise_on=None):
        self.out = {Channel.AGENT: mkwords(agent, Channel.AGENT), Channel.CUSTOMER: mkwords(customer)}
        self.lang, self.prob, self.raise_on = lang, prob, raise_on

    def transcribe(self, samples, sr, channel):
        if self.raise_on == channel:
            raise RuntimeError("decoder failed on 'Laura 612345678'")
        return Transcript(self.out[channel], self.lang, self.prob)


def call(seconds=8):
    rng = np.random.default_rng(1)
    a = rng.normal(0, 0.2, SR * seconds).astype(np.float32)
    c = rng.normal(0, 0.2, SR * seconds).astype(np.float32)
    return CallAudio(a, c, SR, a.tobytes() + c.tobytes())


@pytest.fixture
def dirs(tmp_path):
    d = OutputDirs(tmp_path / "staged", tmp_path / "logs")
    d.staged.mkdir()
    d.logs.mkdir()
    return d


def run(policy, dirs, tr, code="ES-GENERIC-es-S2", **deps):
    d = Deps(transcriber=tr, lexicon=deps.pop("lexicon", Lexicon.empty()), hmac_key=KEY, **deps)
    return process_call(call(), policy.profile(code), policy, d, dirs)


def staged_files(dirs):
    return sorted(p for p in dirs.staged.rglob("*") if p.is_file())


AGENT = "gracias por llamar a Zentrix le atiende Laura en qué puedo ayudarle"
CUSTOMER = "hola me llamo Ana mi teléfono es seis uno dos tres cuatro cinco seis siete ocho"


def test_neutral_call_is_staged_and_redacted(policy, dirs):
    log = run(policy, dirs, FakeTranscriber(AGENT, CUSTOMER))
    assert log.decision.value == "released_to_staging"
    files = staged_files(dirs)
    assert any(p.suffix == ".wav" for p in files) and any(p.suffix == ".json" for p in files)
    transcript = next(p for p in files if p.suffix == ".json").read_text()
    for seeded in ("Zentrix", "Laura", "Ana", "seis uno dos"):
        assert seeded not in transcript


def test_log_line_written_and_has_no_seeded_values(policy, dirs):
    run(policy, dirs, FakeTranscriber(AGENT, CUSTOMER))
    text = (dirs.logs / "calls.jsonl").read_text()
    rec = json.loads(text.strip().splitlines()[-1])
    assert rec["policy_version"] == policy.version
    for seeded in ("Zentrix", "Laura", "Ana", "612345678", "6123", "seis"):
        assert seeded not in text
    # Removal timings are typed ints (ms) and legitimately long; every other field must hold no digit run.
    for r in rec["removals"]:
        assert set(r) == {"category", "channel", "start_ms", "end_ms", "detector", "confidence"}
        assert isinstance(r["start_ms"], int) and isinstance(r["end_ms"], int)
    rest = {k: v for k, v in rec.items() if k not in ("call_id", "removals", "model_versions")}
    assert not re.search(r"\d{4,}", json.dumps(rest))
    assert all(re.fullmatch(r"[0-9a-f]{64}", v) for v in rec["model_versions"].values())


def test_call_id_is_keyed(policy, dirs, tmp_path):
    log1 = run(policy, dirs, FakeTranscriber(AGENT, CUSTOMER))
    import hashlib
    c = call()
    assert log1.call_id != hashlib.sha256(c.source_bytes).hexdigest()


def test_pci_call_dropped_and_nothing_written(policy, dirs):
    log = run(policy, dirs, FakeTranscriber(AGENT, "la tarjeta es 4111 1111 1111 1111"))
    assert log.decision.value == "dropped" and log.drop_reason.value == "pci"
    assert staged_files(dirs) == []
    assert (dirs.logs / "calls.jsonl").exists()


def test_stage_exception_drops(policy, dirs):
    log = run(policy, dirs, FakeTranscriber(AGENT, CUSTOMER, raise_on=Channel.CUSTOMER))
    assert log.decision.value == "dropped" and log.drop_reason.value == "stage_error"
    assert log.error_class == "RuntimeError"
    assert staged_files(dirs) == []
    assert "Laura" not in (dirs.logs / "calls.jsonl").read_text()


def test_language_mismatch_drops(policy, dirs):
    log = run(policy, dirs, FakeTranscriber("thank you for calling", "hello I need help", lang="en", prob=0.97))
    assert log.drop_reason.value == "language_mismatch"
    assert staged_files(dirs) == []


def test_voice_anon_required_without_backend_drops(policy, dirs):
    tr = FakeTranscriber("thank you for calling how can I help", "I want to change my plan", lang="en")
    log = run(policy, dirs, tr, code="US-GENERIC-en-S3")
    assert log.drop_reason.value == "voice_anon_unavailable"
    assert staged_files(dirs) == []


def test_voice_anon_required_rejects_weak_backend(policy, dirs):
    class Weak:
        strength = "weak"
        model_digest = "d" * 64

        def anonymise(self, x, sr):
            return x

    tr = FakeTranscriber("thank you for calling how can I help", "I want to change my plan", lang="en")
    log = run(policy, dirs, tr, code="US-GENERIC-en-S3", voice=Weak())
    assert log.drop_reason.value == "voice_anon_unavailable"


def test_leak_scan_catches_a_first_pass_miss(policy, dirs):
    log = run(policy, dirs, FakeTranscriber(AGENT, "mi referencia es siete ocho nueve cero"),
              detector=lambda *a, **k: [])
    assert log.drop_reason.value == "leak_scan"
    assert staged_files(dirs) == []


def test_empty_transcript_on_speech_drops(policy, dirs):
    log = run(policy, dirs, FakeTranscriber(AGENT, ""))
    assert log.drop_reason.value == "alignment_failure"


def test_redacted_audio_is_filled_at_entity_spans(policy, dirs):
    import wave
    run(policy, dirs, FakeTranscriber(AGENT, CUSTOMER))
    wavs = [p for p in staged_files(dirs) if p.suffix == ".wav"]
    assert len(wavs) == 1
    with wave.open(str(wavs[0])) as w:
        assert w.getnchannels() == 2 and w.getframerate() == SR
        raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, 2)
    cust = raw[:, 1].astype(np.float32) / 32768
    # "seis" is word 7 of CUSTOMER: 2100..2350 ms. That span must be tone, not the original noise.
    seg = cust[int(2.1 * SR):int(2.35 * SR)]
    spec = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(len(seg), 1 / SR)
    assert abs(freqs[np.argmax(spec)] - 1000) < 10


def test_failure_after_partial_write_leaves_no_files(policy, dirs, monkeypatch):
    import deid.pipeline as pl
    real = pl.os.replace
    calls = {"n": 0}

    def flaky(a, b):
        calls["n"] += 1
        if calls["n"] == 2:  # the .wav is already in place; the transcript rename fails
            raise OSError("disk full")
        return real(a, b)

    monkeypatch.setattr(pl.os, "replace", flaky)
    log = run(policy, dirs, FakeTranscriber(AGENT, CUSTOMER))
    assert log.decision.value == "dropped" and log.error_class == "OSError"
    assert staged_files(dirs) == []
