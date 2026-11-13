# deid: rules for agents and contributors

This tree is the call de-identification pipeline. It is staged in `JaymeKame/montu/deid/` and moves to its own
repository (`Montu-lab/deid`) by `git subtree split --prefix=deid`. Nothing here references anything outside
this directory. It never touches the Montu worker app's code or database.

The process rules of `Montu-lab/Montu.app/CLAUDE.md` apply where they are not about Postgres or money. The ones
that bind here:

## Blockers (any one stops a release and stops a merge)
1. An identifier surviving in released output.
2. Raw data able to leave the BPO's environment.
3. PII in a log.
4. An excluded call released.

## Never
- Add a network client, telemetry, update check or licence check. `tests/unit/test_network.py` scans imports.
- Add a free-text field to the call log, or log an exception message, an input filename or matched text.
- Load a model from anything but a local directory.
- Put a rule in `policies/` without a citation or `status = "todo"` + `citation_gap`. Never invent a citation.
- Change a file under `policies/` without a new version (`deid policy-lock --version X.Y.Z`).
- Report synthetic recall as real-world recall.

## Evidence classes. Always label which one you are reporting.
- **UNIT**: `tests/unit`. Pure functions and orchestration with a fake transcriber. Says nothing about models,
  audio quality or recall.
- **PIPELINE**: `tests/pipeline`. Real local models on generated audio. Says the parts connect; not recall.
- **EVAL-SYNTHETIC**: the gold-set report (`deid eval`). Recall and precision on synthetic TTS audio. Binds to the
  generator commit and seed, the TTS voices, the ASR model digest and the policy version. An upper bound on what
  we have shown, never an estimate of real-world recall.
- **EVAL-REAL**: none exists. Nothing may carry this label until plan 001 §11.5 is done.

Never present one class as evidence for another. A green suite says what its assertions bind to, not how many
there are. A skipped test is reported as not run, never as passed.

## Verify, then act
A check and the action it gates are separate commands. Never chain a commit, push or release behind a check.

## Commands
```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest tests/unit          # UNIT
.venv/bin/python -m pytest tests/pipeline      # PIPELINE (needs models in ./models and ffmpeg)
```
