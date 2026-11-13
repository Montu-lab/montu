"""BUILD-TIME ONLY. Downloads model files into ./models so the container can run with no network.
Never imported by the package; the runtime refuses hub ids (deid.asr) and blocks sockets (deid.netguard).
Writes models/MODELS.lock with the SHA-256 of every file, which the BPO can check against its own download."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download

ROOT = Path(__file__).resolve().parents[1] / "models"

ASR = {"faster-whisper-small": "Systran/faster-whisper-small"}
PIPER = [  # (variant, path in rhasspy/piper-voices)
    ("es_ES", "es/es_ES/davefx/medium/es_ES-davefx-medium"),
    ("es_ES", "es/es_ES/sharvard/medium/es_ES-sharvard-medium"),
    ("es_MX", "es/es_MX/ald/medium/es_MX-ald-medium"),
    ("es_MX", "es/es_MX/claude/high/es_MX-claude-high"),
    ("en_US", "en/en_US/lessac/medium/en_US-lessac-medium"),
    ("en_US", "en/en_US/ryan/medium/en_US-ryan-medium"),
]


def main(which: str) -> None:
    if which in ("all", "asr"):
        for name, repo in ASR.items():
            snapshot_download(repo, local_dir=ROOT / "asr" / name)
    if which in ("all", "tts"):
        for _, p in PIPER:
            for ext in (".onnx", ".onnx.json"):
                hf_hub_download("rhasspy/piper-voices", p + ext, local_dir=ROOT / "tts")
            card = str(Path(p).parent / "MODEL_CARD")
            try:
                hf_hub_download("rhasspy/piper-voices", card, local_dir=ROOT / "tts")
            except Exception as exc:  # a missing card is recorded, not hidden
                print(f"no MODEL_CARD for {p}: {type(exc).__name__}", file=sys.stderr)
    lock = {}
    for f in sorted(ROOT.rglob("*")):
        if f.is_file() and ".cache" not in f.parts and f.name != "MODELS.lock":
            lock[str(f.relative_to(ROOT))] = hashlib.sha256(f.read_bytes()).hexdigest()
    (ROOT / "MODELS.lock").write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    print(f"{len(lock)} files locked")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
