# deid

Offline de-identification of two-channel contact-centre recordings. Runs inside the data processor's (BPO's)
environment, with no network at run time. Plan and rationale: `review/requests/001-deid-plan.md`. Network
posture and roles: `docs/network-posture.md`. Rules for contributors: `CLAUDE.md`.

## What it does, per call
1. Decodes the call (stereo, or a dual-mono pair) with the local `ffmpeg`.
2. Transcribes each channel locally (faster-whisper, word timestamps).
3. Drops the call if any exclusion rule of its profile fires (PCI, special categories, minors, vulnerable
   customers), or on language mismatch, unreadable audio, alignment failure, a required-but-missing voice
   anonymiser, or any error. A dropped call writes one log line and nothing else.
4. Detects identifiers (names, brands, cards, IDs, CLABE, IBAN, phone, email, DOB, address, references,
   spelled runs, any 4+ digit run, unclear speech) and fills their audio spans with a tone or silence, plus any
   speech-level audio the ASR did not transcribe.
5. Re-runs the detectors over the redacted transcript; any hit drops the call.
6. Writes redacted stereo WAV + transcript JSON to `out/staged/<batch>/`, one log line per call to
   `out/logs/<batch>.calls.jsonl`, and a manifest of SHA-256 hashes.
7. Nothing reaches `out/released/` until a reviewer approves the exact manifest **and** an evaluation report for
   the same policy and model versions shows no failing category.

## Run
```bash
# build time, with network: fetch models (SHA-256 written to models/MODELS.lock)
python3 -m venv .venv && .venv/bin/pip install -e '.[asr,test]'
HF_HUB_DISABLE_XET=1 .venv/bin/python scripts/fetch_models.py asr

# run time, no network
cat > batch.toml <<'EOF'
profile_code = "ES-GENERIC-es-S2"
channel_map = {agent = 0, customer = 1}
EOF
head -c 32 /dev/urandom > /private/hmac.key          # BPO-held; never leaves the BPO
deid run --input /in --batch-meta batch.toml --out /out --models models \
         --hmac-key-file /private/hmac.key --batch-id B1 [--lexicon /private/lexicon.toml]
deid verify-manifest --out /out --batch-id B1
deid review  --out /out --work /work --batch-id B1 --sample 50     # http://127.0.0.1:8765
deid release --out /out --batch-id B1 --eval-report eval/reports/<report>.json
deid montu-view --out /out ls                                     # what the Montu operator can read
```

`batch.toml` is an allow-list: `profile_code`, `channel_map`, `pairing` and nothing else. Any other key
(a client name, a campaign, a customer id) rejects the batch. Dual-mono: `pairing = "{id}_agent.wav|{id}_customer.wav"`.

`lexicon.toml` (BPO-held, optional): `brands = [...]`, `products = [...]`, `names = [...]` (agent roster). It is
the main lever on brand and agent-name recall; matches are logged by category only.

## Container
```bash
docker build -t deid:0.1.0 .                                                  # GPU (CUDA 12, cuDNN)
docker build --build-arg BASE=python:3.11-slim-bookworm -t deid:0.1.0-cpu .   # CPU
docker run --rm --network none --gpus all \
  -v /mnt/in:/in:ro -v /mnt/private:/private:ro -v /mnt/work:/work -v /mnt/out:/out \
  deid:0.1.0 run --input /in --batch-meta /in/batch.toml --out /out --models /opt/deid/models \
  --hmac-key-file /private/hmac.key --batch-id B1 --device cuda --compute-type float16
```

## Tests and evidence classes
- `pytest tests/unit`: UNIT. Pure functions and orchestration with a fake transcriber.
- `pytest tests/pipeline`: PIPELINE. CLI end to end with the real local ASR on generated audio.
- `python -m deid.eval.run --per-variant N --seed S --out eval-out/X`: EVAL-SYNTHETIC. Recall on synthetic TTS
  calls. **Not real-world recall.** Reports in `eval/reports/` say what they bind to.

## Policies
`policies/` is data, versioned and locked (`POLICY_LOCK.toml`). Every rule cites its source or is marked
`status = "todo"` with a `citation_gap`. Citations are marked `verified = false` until a separate review checks
them against the text. A content change without a new version fails to load. To change a policy:
edit, bump `policies/policy.toml`, then `deid policy-lock --version X.Y.Z`.
