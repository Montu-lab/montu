"""Per-call orchestration. Any exception in any stage drops the call; a dropped call writes a log
record and nothing else.

Order: voice-anon availability -> audio checks -> ASR -> language/alignment checks -> detect -> classify
-> redact -> untranscribed-speech fill -> leak scan -> voice anonymisation -> write.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import __version__
from .asr import Transcriber
from .audio import write_wav
from .calllog import CallLog, CallLogBuilder, ModelSlot
from .classify import classify_call
from .detect.detectors import DetectConfig, detect_channel
from .lexicon import Lexicon
from .policy import PolicySet, Profile
from .redact import apply_audio, plan_spans, redact_transcript_with_times
from .types import Category, Channel, Detector, DropReason, Entity, Word
from .voice import VoiceAnonymiser

SPEECH_DBFS = -40.0  # frame energy above this counts as audio that must be covered by a transcript
UNCOVERED_MIN_MS = 400
COVER_MARGIN_MS = 300


class _Drop(Exception):
    def __init__(self, reason: DropReason):
        self.reason = reason


@dataclass(frozen=True)
class CallAudio:
    agent: np.ndarray
    customer: np.ndarray
    sr: int
    source_bytes: bytes  # raw bytes of the input file(s), in order: hashed (keyed), never stored


@dataclass
class Deps:
    transcriber: Transcriber
    lexicon: Lexicon
    hmac_key: bytes
    voice: VoiceAnonymiser | None = None
    detector: Callable | None = None  # first-pass detector override (tests); leak scan always uses the real one
    language_mismatch_prob: float = 0.8


@dataclass(frozen=True)
class OutputDirs:
    staged: Path
    logs: Path
    batch_id: str | None = None

    @property
    def log_file(self) -> Path:
        return self.logs / (f"{self.batch_id}.calls.jsonl" if self.batch_id else "calls.jsonl")


def call_id(key: bytes, source: bytes) -> str:
    return hmac.new(key, source, hashlib.sha256).hexdigest()


def _rms_dbfs(x: np.ndarray) -> float:
    r = float(np.sqrt(np.mean(np.square(x, dtype=np.float64)))) if len(x) else 0.0
    return 20 * np.log10(r) if r > 0 else -200.0


def _uncovered_speech(x: np.ndarray, sr: int, words: list[Word]) -> list[tuple[int, int]]:
    """Spans with speech-level energy that no transcribed word covers. What the ASR did not read is filled:
    it cannot be checked for identifiers, so it cannot be released."""
    frame = int(0.03 * sr)
    if frame <= 0 or len(x) < frame:
        return []
    covered = np.zeros(len(x) // frame, dtype=bool)
    for w in words:
        a = max(0, (w.start_ms - COVER_MARGIN_MS) * sr // 1000 // frame)
        b = min(len(covered), (w.end_ms + COVER_MARGIN_MS) * sr // 1000 // frame + 1)
        covered[a:b] = True
    spans, start = [], None
    for i in range(len(covered)):
        loud = _rms_dbfs(x[i * frame:(i + 1) * frame]) > SPEECH_DBFS
        if loud and not covered[i]:
            start = i if start is None else start
        elif start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(covered)))
    ms = 30
    return [(a * ms, b * ms) for a, b in spans if (b - a) * ms >= UNCOVERED_MIN_MS]


def _check_audio(call: CallAudio) -> None:
    for x in (call.agent, call.customer):
        if call.sr <= 0 or x is None or len(x) < call.sr // 2 or not np.all(np.isfinite(x)):
            raise _Drop(DropReason.UNREADABLE_AUDIO)
    if _rms_dbfs(call.agent) < -70 and _rms_dbfs(call.customer) < -70:
        raise _Drop(DropReason.UNREADABLE_AUDIO)


def _check_alignment(words: list[Word], x: np.ndarray, sr: int) -> None:
    dur = len(x) * 1000 // sr
    if not words and _rms_dbfs(x) > SPEECH_DBFS:
        raise _Drop(DropReason.ALIGNMENT_FAILURE)
    prev = -1
    for w in words:
        if w.end_ms < w.start_ms or w.start_ms < prev - 50 or w.start_ms > dur + 50:
            raise _Drop(DropReason.ALIGNMENT_FAILURE)
        prev = w.start_ms


def _leak_words(words: list[Word], entities: list[Entity], ch: Channel) -> list[Word]:
    return [Word(t, s, e, 1.0, ch) for t, s, e in redact_transcript_with_times(words, entities)]


def process_call(call: CallAudio, profile: Profile, policy: PolicySet, deps: Deps,
                 dirs: OutputDirs) -> CallLog:
    models = {ModelSlot.ASR: deps.transcriber.model_digest}
    if deps.voice is not None:
        models[ModelSlot.VOICE] = deps.voice.model_digest
    b = CallLogBuilder(call_id=call_id(deps.hmac_key, call.source_bytes), profile_code=profile.code,
                       policy_version=policy.version, pipeline_version=__version__, model_versions=models)
    cid = b._head[0]
    written: list[Path] = []
    try:
        # voice anonymisation availability is checked before any compute
        if profile.voice_anon == "required" and (deps.voice is None or deps.voice.strength != "qualified"):
            raise _Drop(DropReason.VOICE_ANON_UNAVAILABLE)
        if profile.voice_anon == "weak_ok" and deps.voice is None:
            raise _Drop(DropReason.VOICE_ANON_UNAVAILABLE)
        _check_audio(call)
        audio = {Channel.AGENT: call.agent, Channel.CUSTOMER: call.customer}
        trs = {ch: deps.transcriber.transcribe(x, call.sr, ch) for ch, x in audio.items()}
        for ch, tr in trs.items():
            if tr.words and tr.language not in profile.languages and tr.language_prob >= deps.language_mismatch_prob:
                raise _Drop(DropReason.LANGUAGE_MISMATCH)
            _check_alignment(tr.words, audio[ch], call.sr)
        words = {ch: tr.words for ch, tr in trs.items()}
        cfg = DetectConfig(digit_catch_all=profile.digit_catch_all)
        det = deps.detector or detect_channel
        ents: dict[Channel, list[Entity]] = {}
        for ch, tr in trs.items():
            lang = tr.language if tr.language in profile.languages else profile.languages[0]
            ents[ch] = list(det(words[ch], lang, ch, deps.lexicon, cfg))
        lang = trs[Channel.CUSTOMER].language if trs[Channel.CUSTOMER].language in profile.languages \
            else profile.languages[0]
        decision = classify_call(words, [e for es in ents.values() for e in es], profile, lang)
        if decision.drop:
            raise _Drop(decision.reasons[0])
        # leak scan: the real detectors over the redacted transcript. Any hit drops the call.
        for ch in audio:
            lw = _leak_words(words[ch], ents[ch], ch)
            for lg in profile.languages:
                if detect_channel(lw, lg, ch, deps.lexicon, cfg):
                    raise _Drop(DropReason.LEAK_SCAN)
        # audio: entity spans on both channels (crosstalk), plus untranscribed speech per channel
        dur = {ch: len(x) * 1000 // call.sr for ch, x in audio.items()}
        ent_spans = [(e.start_ms, e.end_ms) for es in ents.values() for e in es]
        out_audio = {}
        removals = [(e.category, e.channel, e.start_ms, e.end_ms, e.detector, e.confidence)
                    for es in ents.values() for e in es]
        for ch, x in audio.items():
            unc = _uncovered_speech(x, call.sr, words[ch])
            removals += [(Category.UNCLEAR, ch, s, e, Detector.UNTRANSCRIBED, 0.0) for s, e in unc]
            spans = plan_spans(ent_spans + unc, dur[ch], profile.pad_before_ms, profile.pad_after_ms)
            out_audio[ch] = apply_audio(x, call.sr, spans, profile.fill)
        if profile.voice_anon in ("required", "weak_ok"):
            out_audio[Channel.CUSTOMER] = deps.voice.anonymise(out_audio[Channel.CUSTOMER], call.sr)
        transcript = {"call_id": cid, "policy_version": policy.version, "channels": {
            ch.value: [{"t": t, "s": s, "e": e} for t, s, e in redact_transcript_with_times(words[ch], ents[ch])]
            for ch in audio}}
        dirs.staged.mkdir(parents=True, exist_ok=True)
        wav, js = dirs.staged / f"{cid}.wav", dirs.staged / f"{cid}.json"
        for p in (wav, js):
            written.append(p)
        tmp_wav, tmp_js = wav.with_suffix(".wav.part"), js.with_suffix(".json.part")
        written += [tmp_wav, tmp_js]
        write_wav(tmp_wav, [out_audio[Channel.AGENT], out_audio[Channel.CUSTOMER]], call.sr)
        tmp_js.write_text(json.dumps(transcript, ensure_ascii=False))
        os.replace(tmp_wav, wav)
        os.replace(tmp_js, js)
        for cat, ch, s, e, d, c in removals:
            b.add_removal(category=cat, channel=ch, start_ms=int(s), end_ms=int(e), detector=d, confidence=c)
    except _Drop as d:
        b.drop(d.reason)
    except Exception as exc:  # fail closed: any error drops the call; the message is never logged
        b.error(exc)
    if b.dropped:
        for p in written:
            try:
                p.unlink()
            except FileNotFoundError:
                pass
    log = b.build()
    dirs.logs.mkdir(parents=True, exist_ok=True)
    with open(dirs.log_file, "a") as f:
        f.write(log.to_json() + "\n")
    return log


def log_drop(source_bytes: bytes, profile: Profile, policy: PolicySet, deps: Deps, dirs: OutputDirs,
             reason: DropReason) -> CallLog:
    """A call that never reached process_call (e.g. undecodable): one log record, keyed hash only."""
    b = CallLogBuilder(call_id=call_id(deps.hmac_key, source_bytes), profile_code=profile.code,
                       policy_version=policy.version, pipeline_version=__version__,
                       model_versions={ModelSlot.ASR: deps.transcriber.model_digest})
    b.drop(reason)
    log = b.build()
    dirs.logs.mkdir(parents=True, exist_ok=True)
    with open(dirs.log_file, "a") as f:
        f.write(log.to_json() + "\n")
    return log
