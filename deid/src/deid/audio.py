"""Audio I/O. Decoding goes through the local ffmpeg binary (no network protocols are enabled)."""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

# ffmpeg is told to accept only local files: a crafted input cannot make it open a URL.
_FFMPEG = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file,pipe"]


class UnreadableAudio(Exception):
    pass


def decode(path: Path, sr: int | None = None) -> tuple[np.ndarray, int]:
    """Returns (samples [n, channels] float32 in [-1, 1], sample_rate)."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-select_streams", "a:0",
                            "-show_entries", "stream=sample_rate,channels", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True)
    if probe.returncode != 0 or not probe.stdout.strip():
        raise UnreadableAudio("probe failed")
    rate, ch = probe.stdout.strip().split("\n")[0].split(",")[:2]
    rate, ch = int(rate), int(ch)
    out_sr = sr or rate
    res = subprocess.run(_FFMPEG + ["-i", str(path), "-f", "s16le", "-acodec", "pcm_s16le", "-ar", str(out_sr),
                                    "-ac", str(ch), "-"], capture_output=True)
    if res.returncode != 0 or not res.stdout:
        raise UnreadableAudio("decode failed")
    x = np.frombuffer(res.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return x.reshape(-1, ch), out_sr


def write_wav(path: Path, channels: list[np.ndarray], sr: int) -> None:
    n = min(len(c) for c in channels)
    data = np.stack([np.clip(c[:n], -1, 1) for c in channels], axis=1)
    pcm = (data * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(len(channels))
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
