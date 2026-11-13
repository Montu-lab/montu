# Network posture and roles

Evidence class of this document: design statement. What is enforced in code is marked **(code)** with the test
that holds it; what depends on how the BPO runs the image is marked **(deployment)**.

## No egress at run time
1. **(deployment)** The processing container runs with no network: `docker run --network none ...`, or on
   Kubernetes a pod with a NetworkPolicy denying all egress. This is the control. Nothing in the pipeline needs
   the network.
2. **(code)** `deid.netguard.install()` runs before any input is read (`deid run`, `deid review`). It refuses every
   non-AF_UNIX socket connection and name lookup in the process, and sets `HF_HUB_OFFLINE=1`,
   `TRANSFORMERS_OFFLINE=1`. Test: `tests/unit/test_network.py`. Limit: a C extension opening sockets directly
   bypasses a Python-level guard. That is why (1) is the control.
3. **(code)** The package imports no network client. `test_no_network_imports_in_package` scans every module; the
   only exceptions are named in the test with a reason (`netguard.py`: socket; `review_app.py`: http.server bound
   to 127.0.0.1, urllib.parse for form parsing).
4. **(code)** Models load only from a local directory (`FasterWhisperTranscriber` refuses anything else, and
   passes `local_files_only=True`). Test: `test_asr_refuses_hub_id`.
5. **(code)** `ffmpeg`/`ffprobe` run with `-protocol_whitelist file,pipe`: a crafted input cannot make them open a
   URL.
6. No telemetry, update check or licence server exists in this code. The BPO can verify by reading it and by
   running with (1).

## Storage
The processing container does not talk to cloud storage APIs and holds no cloud credentials. The BPO mounts
buckets as volumes (GCS: Cloud Storage FUSE; S3: Mountpoint for Amazon S3; Azure: BlobFuse2) or stages files in
and out with its own tooling. Open question Q6 in plan 001.

| Mount | Mode | Who may read (BPO IAM) |
|---|---|---|
| `/in` raw audio, `batch.toml` | read-only | BPO only |
| `/private` operator lexicon, HMAC key | read-only | BPO only |
| `/work` review notes | read-write | BPO only |
| `/out/staged` redacted, not yet approved | read-write | BPO only |
| `/out/logs` per-call logs, manifests, approvals | read-write | BPO + Montu operator |
| `/out/released` approved output | read-write | BPO + Montu operator |

## Roles
- **BPO operator**: everything.
- **Montu operator**: `out/logs` and `out/released` only. **(deployment)** Enforced by the BPO's IAM on those
  prefixes. `deid montu-view` reads only those two paths and refuses symlink escapes **(code,
  `test_montu_view_*`)**, but it is a convenience: anyone with a shell in the container can read everything.
  "Montu never reads raw content" holds only if no one at Montu has shell access to the VM (plan Q7).

## What the logs contain
Keyed call id (HMAC-SHA256 with a BPO-held key), profile code, versions, decision, drop reason, exception class
name, and per removal: category, channel, start/end ms, detector, confidence. Never matched text, never an
exception message, never an input filename **(code, `tests/unit/test_calllog.py`,
`tests/pipeline/test_cli_e2e.py::test_logs_carry_no_filename_digits`)**. Approvals record a reviewer code and a
reason code; free-text review notes stay in `/work`.
