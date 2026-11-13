"""UNIT. Dual-mono pairing: files are paired only by the BPO-declared pattern; an unpaired file is one call
that will be dropped as unreadable, never silently merged with another call."""
from deid.cli import _calls


def test_stereo_one_file_per_call(tmp_path):
    for n in ("a.wav", "b.mp3", "notes.txt"):
        (tmp_path / n).write_bytes(b"x")
    assert [[p.name for p in c] for c in _calls(tmp_path, None)] == [["a.wav"], ["b.mp3"]]


def test_dual_mono_pairs_by_pattern(tmp_path):
    for n in ("1_agent.wav", "1_customer.wav", "2_agent.wav", "2_customer.wav", "3_agent.wav"):
        (tmp_path / n).write_bytes(b"x")
    calls = [[p.name for p in c] for c in _calls(tmp_path, "{id}_agent.wav|{id}_customer.wav")]
    assert calls == [["1_agent.wav", "1_customer.wav"], ["2_agent.wav", "2_customer.wav"], ["3_agent.wav"]]
