"""UNIT. Span arithmetic and fills on synthetic arrays."""
import numpy as np

from deid.redact import apply_audio, plan_spans, redact_transcript
from deid.types import Category, Channel, Detector, Entity

from conftest import mkwords


def test_padding():
    assert plan_spans([(1000, 1500)], 10_000, 150, 250) == [(850, 1750)]


def test_merge_after_padding():
    assert plan_spans([(1000, 1500), (1600, 2000)], 10_000, 150, 250) == [(850, 2250)]


def test_clip_to_channel():
    assert plan_spans([(50, 300), (9800, 9990)], 10_000, 150, 250) == [(0, 550), (9650, 10_000)]


def test_unsorted_input():
    assert plan_spans([(5000, 5100), (1000, 1100)], 10_000, 0, 0) == [(1000, 1100), (5000, 5100)]


def test_silence_fill():
    sr = 8000
    x = np.ones(sr * 2, dtype=np.float32)
    y = apply_audio(x, sr, [(0, 500)], "silence")
    assert np.all(y[:4000] == 0)
    assert np.all(y[4000:] == 1)
    assert np.all(x == 1), "input must not be modified in place"


def test_tone_fill_replaces_content():
    sr = 8000
    rng = np.random.default_rng(0)
    x = rng.normal(0, 0.3, sr * 2).astype(np.float32)
    y = apply_audio(x, sr, [(500, 1500)], "tone")
    seg = y[4000:12000]
    spec = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(len(seg), 1 / sr)
    assert abs(freqs[np.argmax(spec)] - 1000) < 5
    rms = float(np.sqrt(np.mean(seg ** 2)))
    assert abs(rms - 0.1 / np.sqrt(2)) < 0.005  # -20 dBFS peak sine
    assert abs(np.corrcoef(seg, x[4000:12000])[0, 1]) < 0.05  # original content gone
    assert np.array_equal(y[:4000], x[:4000])


def test_transcript_tokens():
    w = mkwords("hola soy laura gómez y llamo por")
    e = [Entity(Category.NAME, Channel.CUSTOMER, 2, 3, w[2].start_ms, w[3].end_ms, Detector.NAME_CUE, 0.9)]
    assert redact_transcript(w, e) == ["hola", "soy", "[NAME]", "y", "llamo", "por"]


def test_transcript_no_original_token_survives():
    w = mkwords("mi número es seis uno dos tres cuatro cinco seis siete ocho")
    e = [Entity(Category.PHONE, Channel.CUSTOMER, 3, 11, w[3].start_ms, w[11].end_ms, Detector.PHONE, 0.9)]
    out = redact_transcript(w, e)
    assert out == ["mi", "número", "es", "[PHONE]"]


def test_overlapping_entities_one_token_each_region():
    w = mkwords("a b c d e")
    e = [Entity(Category.NUMBER, Channel.CUSTOMER, 1, 2, 0, 0, Detector.CATCH_ALL_DIGITS, 1.0),
         Entity(Category.CARD, Channel.CUSTOMER, 2, 3, 0, 0, Detector.LUHN, 1.0)]
    assert redact_transcript(w, e) == ["a", "[CARD]", "e"]  # merged region takes the most sensitive type
