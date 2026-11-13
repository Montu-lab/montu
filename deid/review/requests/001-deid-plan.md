# 001 — Call de-identification pipeline ("deid"): plan and red tests

Status: PLAN. Nothing in this document is a measured result unless it says so and names the artefact.
Red tests ship in the same change (`tests/`); they are red by design and name what they bind to.
Reviewer: GPT, sent by Jayme. Blockers for this product (from the brief): an identifier surviving in released
output; raw data able to leave; PII in a log; an excluded call released. Section 3 maps each to its controls and
to the tests that hold it.

---

## 1. Where this lives: a separate repository

**Decision: a separate repository (proposed name `Montu-lab/deid`), staged meanwhile as the self-contained `deid/`
directory on branch `claude/lucid-hamilton-6s6ibs` of `JaymeKame/montu`.** The tree has its own `pyproject.toml`,
tests, policies and process file, and nothing outside `deid/` is referenced, so
`git subtree split --prefix=deid` moves it with history the day the new repository exists.

Why separate, not `deid/` inside `Montu-lab/Montu.app`:

1. **The BPO's security team will read the whole repository we hand them.** `Montu.app` contains worker payment
   logic, production migration controls, the owner-guard limits and internal rulings. None of that is theirs to
   read, and every line of it widens what they must review before they let us in. The deid repository must be
   small enough to audit in a day.
2. **Different gate.** `Montu.app`'s gate is Node + Postgres (`scripts/gate/local-gate.sh`, the `scope` check,
   protected paths). This is Python + local models + audio. Bolting it on means either the gate does not cover it
   (a control that presents itself as covering what it does not: CLAUDE.md, 2026-10-28) or rewriting the gate.
3. **Blast radius.** Nothing here can touch the worker app's code or database if it is not in the same repository.
4. **Licensing posture.** The BPO may ask for the source under escrow or for a licence to inspect. That is a clean
   grant for a single-purpose repository and a messy one for the company's main app.

What I could not do: create the repository (this session may not). **Owner action: create `Montu-lab/deid`
(private), empty.** Plan numbering starts at 001 in that repository's own sequence. (`Montu.app`'s next free number
was 327 when this was written; I did not take it, because the two sequences will diverge.)

The process rules of `Montu.app/CLAUDE.md` apply here as far as they are not about Postgres or money: evidence
classes are labelled; nothing presents itself as a verification of what it did not verify; verify, then act;
the same mistake three times becomes unwritable. `deid/CLAUDE.md` restates the ones that bind this repository.

## 2. What it is, what it is not

A batch program, run by the BPO inside its own environment, that turns two-channel contact-centre recordings into
de-identified audio + transcript + a per-call removal log, plus a batch manifest, and that releases nothing until
a BPO reviewer has approved a recorded sample.

Not in scope now: buyer delivery, billing, the client addendum, any real call data. No component of this plan
contacts Montu, a model hub, a telemetry service or any network at run time.

## 3. The four blockers, mapped to controls and tests

| Blocker | Primary control (prevents) | Second control (detects) | Red tests |
|---|---|---|---|
| Identifier survives in released output | Detectors + catch-all digit-run rule + fail-closed widening; release only of files the pipeline wrote as redacted artefacts | Post-redaction leak scan: detectors re-run over the redacted transcript; a hit drops the call. Human sample review. (Re-ASR of the redacted audio: §8.3, week 2) | `test_detectors_*`, `test_numbers_*`, `test_spelling_*`, `test_redact_*`, `test_pipeline_leak_scan_drops` |
| Raw data able to leave | Processing container runs with no network (`--network none` / no egress rule); in-process socket guard refuses any non-local connection; models load from a local directory only | Static scan: package code imports no network client (`requests`, `urllib.request`, `http.client`, `boto3`, `google.cloud`, `azure`, `socket` outside `netguard`) | `test_netguard_*`, `test_no_network_imports`, `test_asr_refuses_hub_id`, `test_montu_view_*` |
| PII in a log | The log type has no free-text field: every field is an enum, an integer, a float or a hex digest; it is constructed only through a typed builder that refuses anything else; exceptions are recorded by class name only, never message; input filenames never enter the log | Seeded-call test: the serialised log contains none of the seeded identifier strings and no digit run of length ≥ 4 from any of them | `test_calllog_*`, `test_pipeline_log_has_no_seeded_values` |
| Excluded call released | Exclusion classifier runs before any output is written; any exception anywhere in a call's processing is a drop; a drop writes a log entry and nothing else | Release refuses any call whose log says dropped; manifest lists only written outputs | `test_classify_*`, `test_pipeline_drop_*`, `test_release_*` |

The order matters: **prevent first, then detect, then a human samples.** The human sample is not a control on
recall: a reviewer listening to 2% of calls will not find a 1% leak rate. Section 9 says what it is for.

## 4. Trust zones and data flow

```
 BPO environment (their VPC / on-prem)                                     Montu operator can read
 ┌───────────────────────────────────────────────────────────────────┐
 │ input/  (raw audio, batch.toml)        BPO only                    │
 │ private/ (operator lexicon: brands, products, agent roster)  BPO only │
 │ work/   (raw transcripts, intermediates, review DB) BPO only        │
 │                                                                     │
 │  [deid container, --network none]                                   │
 │   ingest → ASR → classify(drop?) → detect → redact → voice anon?    │
 │          → leak scan → write                                        │
 │                                                                     │
 │ out/logs/       per-call logs, batch manifest  ─────────────────────┼──▶ yes
 │ out/staged/     redacted audio + transcripts (not yet approved)     │    no
 │ out/released/   copied from staged/ only after recorded approval ───┼──▶ yes
 └───────────────────────────────────────────────────────────────────┘
```

- **Bucket I/O does not happen inside the processing container.** Reading from a bucket needs network. The
  posture is: the processing container has none. The BPO mounts buckets as volumes (GCS: Cloud Storage FUSE;
  AWS: Mountpoint for S3; Azure: BlobFuse2) or stages files in and out with its own tooling. This keeps "no egress
  at run time" a property of the container, not a promise about our code. Open question Q6.
- **The Montu operator role** is enforced by the BPO's IAM on `out/logs/` and `out/released/` (a separate bucket or
  prefix). The in-container `montu-view` command only reads those two paths and refuses others, but it is a
  convenience, not a control: anyone with shell in the container can read `work/`. Stated so nobody reads it as one.
- **Montu never reads raw audio or raw transcripts** holds only if (a) the IAM grant is as above and (b) nobody at
  Montu has shell on the VM. The second is an operating rule we must commit to in writing, and the BPO's own audit
  log is the evidence, not our code. Open question Q7.

## 5. Per-call processing, with fail-closed rules

Input: one call = either one stereo file (agent and customer on separate channels; which channel is which comes
from the batch metadata, never guessed) or a dual-mono pair matched by a BPO-declared filename pattern. 8 kHz
typical; WAV/OPUS/MP3 decoded by `ffmpeg` (local binary).

| Step | Does | Fails closed how |
|---|---|---|
| 0. Batch metadata | `batch.toml`: `profile_code`, `channel_map`, `pairing` and nothing else. **Allow-list, not deny-list**: any other key, including anything named like a client, a customer or an ID, rejects the batch. Unknown profile code rejects the batch. | Reject whole batch, log reason code. |
| 1. Ingest | Decode, split channels, check duration, sample rate, clipping, silence ratio. | Unreadable, one channel silent > threshold, or channel count wrong → drop. |
| 2. ASR | Per channel, local model, word-level timestamps and per-word probability. Language ID per channel. | Detected language ≠ profile language with probability ≥ τ → drop. Code-switching within a call is tolerated only if the profile lists the second language (e.g. `es` + `en` for US Spanish). Empty transcript on a non-silent channel → drop (alignment failure). |
| 3. Classify | Exclusion rules of the profile over the whole call (both channels). | Any rule fires → drop. Classifier error → drop. |
| 4. Detect | Identifiers, §6. | Detector error → drop. |
| 5. Redact | Audio spans + padding; transcript typed tokens. Low-confidence words within N words of an entity widen the span to include them. | A detected entity whose word timestamps are missing or non-monotonic → drop (alignment failure). |
| 6. Voice | Customer-channel voice anonymisation if the profile requires it. | Required and no qualifying backend installed → drop. |
| 7. Leak scan | Detectors re-run over the redacted transcript. | Any hit → drop. |
| 8. Write | Staged outputs + log line. | Write error → delete partial outputs, log drop. |

A dropped call writes one log record and nothing else; partial files are removed before the record is written.

## 6. Detection

All detectors run over a **normalised view** of each channel's word stream that keeps a pointer from every
normalised character back to the source word index, so a hit always maps back to word timestamps.

### 6.1 Numbers spoken as words
`numbers.py` converts runs of number words to digit strings, per language: `es`, `en` first; `pt`, `fr`, `it`, `de`
after the pilot language is fixed.
- Digit-by-digit: "cuatro cinco dos uno" → `4521`.
- Grouped: "cuarenta y cinco, veintiuno" → `4521`; "forty five twenty one" → `4521`. Ambiguity ("cien" vs "ciento")
  is resolved toward producing the digit run, never toward dropping it.
- Repeats: "doble cinco", "double five", "triple zero" → `55`, `000`.
- "o"/"oh" for zero in English; "cero" in Spanish.
- Mixed digits and words (ASR output often mixes them: "4 cinco 2 1") → joined.
- Fillers and hesitations inside a run ("eh", "um", "a ver") do not break it; up to K filler tokens are skipped.
- Runs across ASR word boundaries and across short pauses (< P ms) are joined.

### 6.2 Spelled letters
"eme, a, erre, i, a" / "M as in Mike, A, R..." / "be de burro" → `MARIA`, with the run mapped to word indices.
Any spelled run of length ≥ 3 is redacted as `[SPELLED]` regardless of what it spells: a spelled run on a support
call is almost always a name, an email or a reference. This is a recall-first rule; precision cost is accepted.

### 6.3 Structured identifiers (validated where a checksum exists)
| Category | Token | Rule |
|---|---|---|
| Payment card | `[CARD]` | 13–19 digits, Luhn-valid. **Any Luhn-valid run also triggers the PCI drop (§7).** |
| CVV / card expiry | `[CARD]` | Cue words ("código de seguridad", "CVV", "caducidad", "expiry") + 3–4 digits or a date → PCI drop. |
| IBAN | `[IBAN]` | Country code + mod-97 valid. Spoken IBANs are long digit runs; they also hit the catch-all. |
| CLABE (MX) | `[ACCOUNT]` | 18 digits, weighted check digit (3,7,1). |
| Account number (generic) | `[ACCOUNT]` | Cue word + digit run ≥ 6. |
| DNI / NIE (ES) | `[NATIONAL_ID]` | 8 digits + check letter (mod 23); NIE X/Y/Z prefix. |
| CURP (MX) | `[NATIONAL_ID]` | 18-char pattern + check digit. |
| RFC (MX) | `[NATIONAL_ID]` | 12/13-char pattern. |
| CPF (BR) | `[NATIONAL_ID]` | 11 digits, two mod-11 check digits. |
| SSN (US) | `[NATIONAL_ID]` | 9 digits with cue, or AAA-GG-SSSS shape. |
| Phone | `[PHONE]` | Per-country lengths (ES 9, MX 10, US 10, +country code). |
| Email | `[EMAIL]` | Spoken form: "arroba"/"at", "punto"/"dot", "guion bajo"/"underscore"; written form. |
| Date of birth | `[DOB]` | Date expression within N words of a cue ("fecha de nacimiento", "nací", "date of birth", "born"). Any full date (day+month+year) spoken by the customer is redacted even without a cue. |
| Order / ticket / booking ref | `[REFERENCE]` | Cue word + alphanumeric run ≥ 4; spelled runs (§6.2). |
| Postal address | `[ADDRESS]` | Street-type cue ("calle", "avenida", "colonia", "street", "avenue") + following words up to a boundary; postal codes (ES 5 digits, MX 5, US 5/9) with cue. |

**Catch-all (default on, every profile): any digit run of ≥ 4 digits in either channel is redacted as `[NUMBER]`
whatever it is.** Both channels, because agents read numbers back. Reason: unknown account formats are the commonest structured
leak, and a de-identified support call loses little by losing its numbers. Money amounts and times are the
precision cost; Q10 asks whether buyers care.

### 6.4 Names
- **Operator lexicon (BPO-held, `private/lexicon.toml`)**: client brand names, product names, agent roster first
  names and surnames. The BPO already holds these; we never see them. They are matched case- and accent-insensitive,
  including inside compounds. Hits are logged as category only. **This is the main recall lever for brand and agent
  names, and it is why the brand-in-greeting case is tractable.** Q3 asks whether the BPO will provide it.
- **Greeting slot**: in the agent channel's first 20 s, the noun phrase after "bienvenido a", "gracias por llamar a",
  "le atiende", "mi nombre es", "thank you for calling", "you're speaking with", "my name is" is redacted as `[BRAND]`
  or `[NAME]` regardless of lexicon.
- **Self-introduction cues** in both channels ("me llamo", "soy", "a nombre de", "my name is", "this is").
- **Statistical NER**: a local multilingual NER/PII model for names outside the cues. Candidate: GLiNER multi PII
  (Apache-2.0) or spaCy `xx`/`es`/`en` pipelines; chosen by the gold-set measurement, not now. Week 2.
- **Name gazetteer**: first names and surnames for ES/MX/US from public frequency lists, as a recall backstop for
  ASR-lowercased output.

### 6.5 Low ASR confidence
A word with probability < c_low within W words of a detected entity is folded into that entity. A run of ≥ 3
low-confidence words in the customer channel with no entity nearby is redacted as `[UNCLEAR]`: what the ASR could
not read, a buyer cannot use and we cannot vouch for.

## 7. Exclusion classifier (drop the call)

Rules are data (§10). Each rule: id, category, languages, trigger (lexicon, entity, or model), threshold, citation.

| Category | Default | Day-3 mechanism | Later |
|---|---|---|---|
| PCI: card number, CVV, expiry spoken | drop | Luhn hit, or card cue + digits | same; it is already deterministic |
| Special categories (health, religion, sexuality, union, ethnicity, political opinion, genetic, biometric) | drop | Per-language lexicons, recall-tuned (they will over-drop) | Local zero-shot classifier (NLI or small local LLM) as a second voter; drop if either fires |
| Minors (a minor's voice or a call about a minor's data) | drop | Lexicon cues ("mi hijo", "tiene 12 años", "my son", "he's 15") + age expressions < 18 | Voice-age estimation on the customer channel: unmeasured, may not be good enough at 8 kHz |
| Vulnerable customers (hardship, collections, distress, bereavement) | drop | Lexicons + sector rule (a `collections` sector profile drops everything) | Classifier as above |
| Language mismatch / unreadable / alignment failure | drop | §5 | — |

**The day-3 classifier will over-drop.** That is the right failure direction. Its precision is measured and
reported (confusion matrix, §11) so the commercial cost of over-dropping is a number, not a feeling.

## 8. Audio redaction and voice anonymisation

### 8.1 Redaction
Span = [first word start − pad_before, last word end + pad_after], clipped to the channel, merged when gaps < g ms.
Default pads 150 ms / 250 ms: word timestamps from attention-based alignment are known to drift; the pads are set
by the gold-set measurement of boundary error, not now. Fill = silence, or a 1 kHz tone at −20 dBFS, per profile.
Both channels are redacted at the same spans when the entity was spoken on one channel and crosstalk could carry
it on the other (default on).

### 8.2 Voice anonymisation (customer channel, per profile)
Interface in day 1; qualified backend later. Candidates, all local:
- McAdams-coefficient spectral transform (signal processing, no model). Cheap; the VoicePrivacy Challenge
  literature reports it as weak against an attacker who knows the method. **Allowed only for profiles marked
  `voice_anon = "weak_ok"`.**
- kNN-VC / neural resynthesis to a pool of target voices. Stronger, costs GPU, must be measured for content
  preservation (WER before/after) and protection (speaker-verification EER, ignorant and lazy-informed attacker).
- ASR → TTS resynthesis: strongest unlinkability, loses prosody and paralinguistics, which buyers may want.

A profile requiring `voice_anon = "required"` drops every call until a backend with a recorded evaluation is
installed. That is the honest default for BIPA-exposed US profiles.

### 8.3 Leak check on the audio (week 2)
Re-run ASR over the redacted audio and run the detectors on the result. This catches a misaligned span that left
digits audible. It doubles ASR cost; the cheaper half (re-detect over the redacted transcript) is in from day 1.

## 9. Log, manifest, review, release

### 9.1 Per-call log (`out/logs/calls.jsonl`)
```
call_id          hex   HMAC-SHA256(bpo_key, raw bytes of the call's files in order)
profile_code     enum  (from the policy set)
policy_version   str   from the policy files, checked against the lock
model_versions   map   enum name → hex digest of the model files
decision         enum  released_to_staging | dropped
drop_reason      enum  | null
removals[]       {category: enum, channel: agent|customer, start_ms: int, end_ms: int,
                  detector: enum, confidence: float}
error_class      enum  | null   (exception class name from a closed list; never the message)
pipeline_version str   package version
```
- **No free-text field exists.** Strings are accepted only from closed enums or as validated hex digests or
  semver. The builder refuses anything else (`test_calllog_rejects_free_text`).
- **Input filenames never enter the log.** BPO filenames routinely carry phone numbers or ticket ids.
- **Why HMAC, not a plain hash:** a plain SHA-256 of the audio lets anyone holding the raw file confirm it is in the
  dataset. Keyed with a BPO-held key, only the BPO can link output to source. Q8.
- Removal timestamps and categories are not PII by themselves; together with the released audio they say where
  something was removed, which buyers need. They never say what.

### 9.2 Manifest
`out/logs/manifest-<batch>.json`: every staged output file with SHA-256, size, call_id; the policy and model
versions; counts by decision and drop reason. `deid verify-manifest` recomputes.

### 9.3 Review tool and release
- `deid review --batch B`: a local web page bound to `127.0.0.1` (the reviewer reaches it through the BPO's own
  tunnel), random sample of n calls (seeded, seed recorded), plays redacted audio, shows redacted transcript and
  log side by side, approve or reject with a reason code (+ optional note stored in `work/`, BPO-only, never copied
  to `out/`).
- `deid release --batch B`: refuses unless a recorded approval exists for that batch's manifest digest, and copies
  `staged/` → `released/` only for calls whose log says `released_to_staging`. A batch with any rejected sample is
  not releasable until the cause is fixed and the batch re-run (Q9 for the BPO's preferred rule).
- **What the sample review is and is not.** It catches systematic failures: a wrong channel map, a brand missed in
  every greeting, a tone at the wrong place, a profile misconfigured. It does not measure recall. A 50-call sample
  with zero leaks bounds the per-call leak rate at about 6% (95%, rule of three: 3/50), which is not a privacy
  guarantee. Recall is measured on the gold set (§11) and, later, on a labelled real sample (§11.5).

## 10. Policies as data

- `policies/profiles.toml`: profile code → sector, jurisdiction, language(s), strictness, voice_anon, fill mode.
- `policies/jurisdictions/{ES,MX,CO,BR,AR,US}.toml`: rules. **Every rule carries a citation, or `status = "todo"`
  with `citation_gap = "..."`. The loader refuses a rule with neither.** A TODO rule does not run; its existence is
  reported in every batch summary for that jurisdiction ("3 rules uncited for MX").
- `policies/POLICY_LOCK.toml`: per file, version and SHA-256. A content change without a version bump fails the
  test suite (`test_policy_lock_*`). The version recorded in every log line is the policy set's version.
- **Citation status.** Every citation in this commit is entered from memory and marked `verified = false`. None
  may be quoted externally until a separate review checks it against the text (standing instruction). The citations
  in the brief (EDPB Guidelines 02/2026, CJEU C-413/23 P) are recorded as provided by the owner, unverified here.

| Jurisdiction | Encoded now (unverified citations) | TODO, citation gap |
|---|---|---|
| ES (GDPR + LOPDGDD) | GDPR Art. 9(1) special categories → drop; LOPDGDD Art. 7 (minors' consent age 14) → minors drop; PCI DSS v4 Req. 3.3.1 → card drop | LOPDGDD Art. 9 scope vs GDPR Art. 9; any sector-specific rule (telecom, banking) |
| MX (LFPDPPP 2025) | PCI → card drop | Article numbers for "datos personales sensibles" and minors in the 2025 law: not known reliably; TODO |
| CO (Ley 1581/2012) | Art. 5 sensitive data → drop; Art. 7 minors → drop | Decreto 1377/2013 specifics |
| BR (LGPD) | Art. 5 II sensitive data → drop; Art. 14 children/adolescents → drop; Art. 12 anonymised data outside the law unless reversible by reasonable means (informs the standard, not a rule) | ANPD guidance on anonymisation |
| AR (Ley 25.326) | Art. 2 sensitive data, Art. 7 → drop | Successor bill status |
| US | PCI → card drop; BIPA 740 ILCS 14/10 voiceprint is a biometric identifier → `voice_anon = "required"` for IL-exposed profiles; HIPAA 45 CFR 164.514(b)(2) safe-harbour identifiers → health sector drop or redact | Which state laws beyond IL (TX CUBI, WA) apply to the BPO's US callers |

## 11. Evaluation

### 11.1 Gold set
Synthetic two-channel calls, Spanish (Spain), Spanish (Mexico), English (US). Generated offline:
- Scripts from templates with seeded identifiers in every category of §6.3 and every spoken format (digit-by-digit,
  grouped, double/triple, mixed, spelled, with fillers).
- TTS: Piper (local, ONNX, has `es_ES`, `es_MX`, `en_US` voices; each voice's licence is checked before use and
  recorded). **Each phrase is synthesised separately and concatenated**, so every identifier's start and end in
  milliseconds is exact by construction, not by alignment. Word-level labels within a phrase come from the
  script; their timestamps are interpolated and labelled as such.
- Telephony simulation: resample to 8 kHz, G.711 μ-law round trip, band-pass 300–3400 Hz, noise at several SNRs.
- Hard cases: brand in greeting, agent name in greeting, digits in groups, spelled names, crosstalk (customer speaks
  over the agent's read-back), hold music (synthetic, local), IVR prompts, code-switching (es↔en), numbers broken by
  fillers.
- Exclusion cases: one per drop category per language, plus near-misses that must **not** drop (e.g. "the card
  arrived" with no digits) to measure over-dropping.
- Target size for the first report: 300 calls per language variant. The generator is deterministic from a seed;
  the seed is in the report.

### 11.2 Metrics
- **Entity recall, strict:** an entity counts as removed only if 100% of its gold audio span is inside redacted
  audio **and** every gold token is replaced in the transcript. Partial cover is a miss: three digits of a card
  left audible is a leak.
- **Precision:** fraction of redacted milliseconds (and tokens) that overlap any gold entity.
- Per category × language variant, with Wilson 95% intervals. With 300 calls a category seeded once per call gives
  n ≈ 300; a measured recall of 300/300 still only bounds true recall at ≥ 99.0% (one-sided 95%). We say that
  next to every 100%.
- **Drop classifier:** confusion matrix per category and language (true drop / false drop / missed drop / true
  keep), with the missed-drop count stated first.
- **Leak rate per call:** fraction of released calls with any surviving gold entity. This is the number a buyer's
  lawyer will ask for.
- Throughput: real-time factor and calls/hour on one GPU, measured on the target VM type, with model, precision and
  batch size named. **Not measurable in this session (no GPU); a CPU figure will be reported as a CPU figure.**

### 11.3 Targets per category, and what happens below
Targets are on the synthetic gold set. They are our bar for "the pipeline does what it claims on audio we
control", not a real-world recall claim.

| Category | Target strict recall (synthetic) | Below target |
|---|---|---|
| Excluded calls (all drop categories) | 0 missed drops on the gold set | Blocker. No release under any profile. |
| Card (incl. drop trigger) | 100% | Blocker. |
| National ID, IBAN, CLABE, account, phone | ≥ 99% | Category marked `failing` in the eval report bound to that model+policy version; `release` refuses for profiles that list it as required, until fixed. |
| Email, reference | ≥ 98% | Same. |
| Brand (with operator lexicon) | ≥ 99% | Same. Without a lexicon: reported separately, no target, and the profile must say `brand_lexicon = "absent"`, which is printed on the manifest. |
| Person names | ≥ 95% | Same, plus fallback: drop any call where a name cue fires and no name was detected after it. |
| Address, DOB | ≥ 95% | Same, plus fallback: cue without a detected entity → drop. |
| Precision (all) | reported, no gate | Over-redaction costs buyer value, not privacy. |

`release` reads the eval report whose digest matches the installed model and policy versions. No matching report,
or a failing required category: refuses, and says which.

### 11.4 What the evaluation binds to (said every time it is reported)
- Synthetic TTS speech is cleaner, more regular and less accented than real callers. Real telephony has codec
  artefacts, packet loss, background noise, emotional speech, regional accents, real names outside any gazetteer.
  **Synthetic recall is an upper bound on what we have shown, not an estimate of real-world recall.** It is never
  to be reported as real-world recall.
- The gold set measures our detectors on our generator's distribution of formats. A format we did not think of is
  neither in the generator nor measured.
- Results bind to: the generator commit and seed, the TTS voices, the ASR model and its digest, the policy version.

### 11.5 What real-audio evaluation needs
- Controller authorisation for evaluation as a purpose (Q1).
- A random sample of real calls from the pilot client (not cherry-picked), of a size chosen for the bound we want
  (≈ 300 calls for a ±1-point bound at ~99%).
- Double annotation by BPO staff inside the BPO environment, with the annotation tool running there; disagreement
  adjudicated; inter-annotator agreement reported.
- Montu sees only aggregate metrics, never the annotations' content.

## 12. Packaging and posture

- One container image: Python 3.11+, `ffmpeg`, CTranslate2/faster-whisper, model files baked in or mounted
  read-only (Q5). CUDA base image for GPU; CPU fallback for tests.
- Run: `docker run --network none --gpus all -v in:/in:ro -v private:/private:ro -v work:/work -v out:/out deid run`.
- `deid/netguard.py` refuses any socket connection that is not AF_UNIX at process start, and sets
  `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`. Belt and braces: the container's network namespace is the real
  control; the guard turns an accidental call into a loud failure instead of a silent timeout.
- GCP first (GPU VM, e.g. L4), AWS and Azure next: nothing in the image is cloud-specific because the container never
  talks to a cloud API. The difference between clouds is only how the BPO mounts storage.
- No telemetry, no update check, no licence server. The image is reproducible from the repository; the BPO can
  build it themselves.

## 13. Red tests in this change

All UNIT-class (pure functions, deterministic fakes for ASR). They are red now because the functions raise
`NotImplementedError`; each asserts the specific outcome, not just "raises".

- `tests/unit/test_metadata.py`: allow-list; a `client_name` key, a `customer_id` key, any unknown key, an unknown
  profile → batch rejected with the specific reason code.
- `tests/unit/test_numbers.py`: es/en digit-by-digit, grouped, double/triple, mixed digits and words, fillers inside
  runs; word-index provenance is exact.
- `tests/unit/test_spelling.py`: es letter names, en NATO/"as in", run ≥ 3 → spelled entity.
- `tests/unit/test_checksums.py`: Luhn, IBAN, DNI, NIE, CPF, CLABE, CURP shape; valid and invalid of each.
- `tests/unit/test_detectors.py`: card from spoken words, phone, email spoken, DNI, CLABE, brand from lexicon,
  brand from greeting slot without lexicon, agent name in greeting, catch-all digit run, low-confidence widening.
- `tests/unit/test_classify.py`: card → drop(pci); CVV cue → drop(pci); health / religion lexicon → drop; minor cue
  → drop; vulnerable cue → drop; neutral call → keep; "card arrived" without digits → keep.
- `tests/unit/test_redact.py`: span with padding, merging, clipping; silence and tone fill; transcript tokens; no
  original token survives in the redacted transcript.
- `tests/unit/test_calllog.py`: free text refused; filename never present; error recorded as class only; serialised
  log of a seeded call contains no seeded value or 4-digit substring of one.
- `tests/unit/test_policy.py`: rule without citation or todo refused; content change without version bump fails;
  policy version present in every log record.
- `tests/unit/test_pipeline.py` (fake ASR): excluded call writes only a log; exception in a stage → drop;
  language mismatch → drop; voice anon required without backend → drop; leak scan hit → drop; dropped call leaves
  no files.
- `tests/unit/test_release.py`: release refused without approval, refused for a manifest digest that changed after
  approval, never copies a dropped call; manifest verify detects tampering; Montu view refuses `work/`.
- `tests/unit/test_netguard.py` + `test_no_network_imports.py`: connect refused after install; package source
  imports no network client; ASR loader refuses a hub id.

Evidence class vocabulary for this repository (also in `deid/CLAUDE.md`):
- **UNIT**: `tests/unit`. Pure functions and orchestration with fake ASR. Says nothing about models or audio quality.
- **PIPELINE**: `tests/pipeline`. Real local models on generated audio. Says the parts connect; not recall.
- **EVAL-SYNTHETIC**: the gold-set report. Recall/precision on synthetic audio, bound as in §11.4.
- **EVAL-REAL**: none exists. Nothing may be labelled with it until §11.5 is done.

## 14. Schedule, honestly

Day counts are build days from the start of implementation, on CPU here and on a GPU VM when we have one.

**By day 3 (expected, not measured):**
- Metadata allow-list, policy loader + lock, typed log, manifest, release gate, Montu view, net guard.
- faster-whisper ASR with word timestamps, run on CPU; GPU path untested until a GPU exists.
- Number normalisation and spelled letters for `es` and `en`; checksum and regex detectors; catch-all digit rule;
  lexicon and greeting-slot brand/name detection; low-confidence widening.
- Lexicon exclusion classifier for `es`/`en` (will over-drop).
- Audio redaction (silence/tone) and transcript tokens; leak re-scan on the transcript.
- Container that runs offline end to end on a CPU.
- A first gold set (smaller than 300/variant) and a first per-category report, labelled EVAL-SYNTHETIC.

**Takes longer (week 2+), and why:**
- Voice anonymisation with a measured protection figure: needs a speaker-verification attacker set-up and a
  content-preservation measurement. Until then `required` profiles drop everything.
- Drop-classifier quality beyond lexicons: needs a local model and a labelled near-miss set; lexicons over-drop.
- Number words in `pt`, `fr`, `it`, `de`: each language's grouping conventions ("quatre-vingt-dix", "einundzwanzig")
  is a few hours with tests, but it is not needed until the pilot language is known (Q2).
- Statistical NER for names outside cues and lexicon: model choice is a measurement.
- Audio-side leak check (re-ASR of redacted audio).
- Throughput on one GPU: needs the GPU.
- Real-audio evaluation: needs §11.5.

**One-week promise.** The brief promised a first de-identified sample within one week of access to a machine in
the BPO's environment. Achievable for one language with the day-3 scope **if** (a) the profile does not require
voice anonymisation, (b) the BPO supplies a lexicon or accepts lexicon-free brand detection with its gap stated on
the manifest, (c) the pilot language is `es` or `en`. If the pilot needs voice anonymisation, the honest answer is
a sample in which every call is dropped, or a sample under a `weak_ok` profile that says so.

## 15. Evidence records

No external claim is made in this plan. Before any sentence about this pipeline's performance goes to the BPO or a
buyer, it gets a record: exact sentence; status (measured / published / estimate / hypothesis); source (eval report
path + commit); population (synthetic, variant, n); task; model versions; metric; comparator; assumptions. Evidence
about Whisper's general WER is not evidence about this pipeline's recall. A synthetic result is not a real-audio
result. A Spain result is not a Mexico result.

## 16. Open questions (not guessed)

- **Q1.** Has the pilot client (controller) authorised (a) the anonymisation processing and (b) licensing of the
  output, in writing, and does that authorisation cover using real calls to evaluate the pipeline (§11.5)?
- **Q2.** Pilot language and jurisdiction: which one? It decides which number grammar and which jurisdiction profile
  must be complete on day 1.
- **Q3.** Will the BPO supply a private lexicon (brand, products, agent roster) inside its environment?
- **Q4.** Sector of the pilot client. Collections, healthcare, insurance claims or banking hardship change the
  default from "redact" to "drop most calls".
- **Q5.** Model weights: may we bake them into the image (bigger image, fully reproducible) or must they be mounted
  from a BPO-controlled store? Either way, which models' licences does the BPO's legal team accept (Whisper weights:
  MIT; Piper voices: per voice)?
- **Q6.** Storage: will the BPO mount buckets as volumes, or stage files in and out itself? We do not want the
  processing container to hold cloud credentials.
- **Q7.** Who at Montu, if anyone, gets shell on the VM during the pilot? Our claim "Montu never reads raw content"
  needs the answer to be "nobody", or a BPO-supervised session with their audit log.
- **Q8.** Call identity: HMAC with a BPO-held key (proposed) acceptable? Who generates and holds it?
- **Q9.** Release rule after a rejected sample: re-run the whole batch, or drop the rejected calls and re-sample?
- **Q10.** Do buyers want amounts, times and quantities (lost to the catch-all digit rule)? If yes, which formats
  can be shown not to be identifiers?
- **Q11.** Channel map: is agent/customer on a fixed channel per platform, and does the BPO's platform export dual-mono
  with a stable naming pattern?
- **Q12.** Retention: how long may `work/` (raw transcripts) live? Default proposed: deleted at batch release.
- **Q13.** Are IVR prompts and hold segments part of the recording? They carry the brand.
- **Q14.** Does the BPO's US operation take calls from Illinois residents (BIPA), and are any US clients HIPAA covered
  entities?
- **Q15.** EDPB Guidelines 02/2026 and CJEU C-413/23 P: who on our side verifies the citations and their reading
  before the client addendum relies on them?
