"""UNIT. Manifest, approval, release and the Montu view, on a temporary directory tree."""
import json

import pytest

from deid.manifest import build_manifest, manifest_digest, verify_manifest
from deid.release import ReleaseRefused, record_approval, release
from deid.roles import AccessRefused, MontuView

A, B, C = "a" * 64, "b" * 64, "c" * 64
EVAL_OK = {"policy_version": "0.1.0", "model_versions": {"asr": "e" * 64}, "failing_categories": []}


@pytest.fixture
def out(tmp_path):
    root = tmp_path / "out"
    st = root / "staged" / "B1"
    st.mkdir(parents=True)
    (root / "logs").mkdir()
    for cid in (A, B):
        (st / f"{cid}.wav").write_bytes(b"RIFF" + cid.encode())
        (st / f"{cid}.json").write_text("{}")
    lines = [{"call_id": A, "decision": "released_to_staging"}, {"call_id": B, "decision": "released_to_staging"},
             {"call_id": C, "decision": "dropped", "drop_reason": "pci"}]
    (root / "logs" / "B1.calls.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    (root / "work").mkdir()
    (root / "work" / "raw-transcript.json").write_text("secret")
    m = build_manifest(st, "B1", "0.1.0", {"asr": "e" * 64})
    (root / "logs" / "B1.manifest.json").write_text(json.dumps(m))
    return root


def digest(out):
    return manifest_digest(json.loads((out / "logs" / "B1.manifest.json").read_text()))


def test_manifest_lists_every_file_with_sha256(out):
    m = json.loads((out / "logs" / "B1.manifest.json").read_text())
    assert len(m["files"]) == 4 and all(len(f["sha256"]) == 64 for f in m["files"])
    assert verify_manifest(out / "staged" / "B1", m) == []


def test_manifest_detects_tamper_and_extra(out):
    st = out / "staged" / "B1"
    m = json.loads((out / "logs" / "B1.manifest.json").read_text())
    (st / f"{A}.json").write_text('{"x": 1}')
    (st / "extra.wav").write_bytes(b"x")
    assert sorted(verify_manifest(st, m)) == sorted([f"{A}.json", "extra.wav"])


def test_release_refused_without_approval(out):
    with pytest.raises(ReleaseRefused) as e:
        release(out, "B1", EVAL_OK)
    assert e.value.reason == "no_approval"


def test_release_refused_when_rejected(out):
    record_approval(out, "B1", digest(out), "reviewer-1", approved=False, reason_code="leak_heard")
    with pytest.raises(ReleaseRefused) as e:
        release(out, "B1", EVAL_OK)
    assert e.value.reason == "rejected"


def test_release_refused_if_staged_changed_after_approval(out):
    record_approval(out, "B1", digest(out), "reviewer-1", approved=True, reason_code="ok")
    (out / "staged" / "B1" / f"{A}.wav").write_bytes(b"changed")
    with pytest.raises(ReleaseRefused) as e:
        release(out, "B1", EVAL_OK)
    assert e.value.reason == "manifest_changed"


def test_release_refused_if_dropped_call_has_output(out):
    (out / "staged" / "B1" / f"{C}.wav").write_bytes(b"should not exist")
    m = build_manifest(out / "staged" / "B1", "B1", "0.1.0", {"asr": "e" * 64})
    (out / "logs" / "B1.manifest.json").write_text(json.dumps(m))
    record_approval(out, "B1", manifest_digest(m), "reviewer-1", approved=True, reason_code="ok")
    with pytest.raises(ReleaseRefused) as e:
        release(out, "B1", EVAL_OK)
    assert e.value.reason == "dropped_call_has_output"


def test_release_refused_without_matching_eval(out):
    record_approval(out, "B1", digest(out), "reviewer-1", approved=True, reason_code="ok")
    with pytest.raises(ReleaseRefused) as e:
        release(out, "B1", None)
    assert e.value.reason == "no_eval_report"
    with pytest.raises(ReleaseRefused) as e:
        release(out, "B1", {**EVAL_OK, "policy_version": "0.0.9"})
    assert e.value.reason == "no_eval_report"
    with pytest.raises(ReleaseRefused) as e:
        release(out, "B1", {**EVAL_OK, "failing_categories": ["NAME"]})
    assert e.value.reason == "eval_failing"


def test_release_copies_only_staged_calls(out):
    record_approval(out, "B1", digest(out), "reviewer-1", approved=True, reason_code="ok")
    ids = release(out, "B1", EVAL_OK)
    assert sorted(ids) == sorted([A, B])
    rel = sorted(p.name for p in (out / "released" / "B1").iterdir())
    assert rel == sorted([f"{A}.wav", f"{A}.json", f"{B}.wav", f"{B}.json"])


def test_montu_view_reads_logs_and_released_only(out):
    v = MontuView(out)
    assert v.read("logs/B1.calls.jsonl")
    for bad in ("work/raw-transcript.json", "staged/B1/" + A + ".wav", "../out/work/raw-transcript.json",
                "logs/../work/raw-transcript.json", "/etc/passwd"):
        with pytest.raises(AccessRefused):
            v.read(bad)


def test_montu_view_refuses_symlink_escape(out):
    (out / "logs" / "link").symlink_to(out / "work" / "raw-transcript.json")
    with pytest.raises(AccessRefused):
        MontuView(out).read("logs/link")


def test_montu_view_list_excludes_work_and_staged(out):
    names = MontuView(out).list()
    assert names and all(n.startswith(("logs/", "released/")) for n in names)
