"""UNIT. The log cannot carry free text. This is the structural control for 'PII in a log'."""
import dataclasses
import json

import pytest

from deid.calllog import CallLog, CallLogBuilder, LogFieldError, ModelSlot
from deid.types import Category, Channel, Detector, DropReason

HEX = "a" * 64


def builder(**kw):
    args = dict(call_id=HEX, profile_code="ES-GENERIC-es-S2", policy_version="0.1.0",
                pipeline_version="0.1.0", model_versions={ModelSlot.ASR: "b" * 64})
    args.update(kw)
    return CallLogBuilder(**args)


def test_valid_log_round_trips():
    b = builder()
    b.add_removal(category=Category.NAME, channel=Channel.CUSTOMER, start_ms=100, end_ms=900,
                  detector=Detector.NAME_CUE, confidence=0.91)
    d = json.loads(b.build().to_json())
    assert d["call_id"] == HEX and d["policy_version"] == "0.1.0" and d["decision"] == "released_to_staging"
    assert d["removals"] == [{"category": "NAME", "channel": "customer", "start_ms": 100, "end_ms": 900,
                              "detector": "name_cue", "confidence": 0.91}]


@pytest.mark.parametrize("kw", [
    {"call_id": "call-from-612345678"},
    {"profile_code": "Movistela premium line"},
    {"policy_version": "0.1.0 laura"},
    {"pipeline_version": "x" * 200},
    {"model_versions": {ModelSlot.ASR: "whisper large from laura's laptop"}},
    {"model_versions": {"asr": "b" * 64}},
])
def test_free_text_refused_in_header(kw):
    with pytest.raises(LogFieldError):
        builder(**kw)


def test_removal_fields_must_be_typed():
    b = builder()
    with pytest.raises(LogFieldError):
        b.add_removal(category="NAME: Laura", channel=Channel.CUSTOMER, start_ms=0, end_ms=1,
                      detector=Detector.NAME_CUE, confidence=0.5)
    with pytest.raises(LogFieldError):
        b.add_removal(category=Category.NAME, channel=Channel.CUSTOMER, start_ms="0", end_ms=1,
                      detector=Detector.NAME_CUE, confidence=0.5)
    with pytest.raises(LogFieldError):
        b.add_removal(category=Category.NAME, channel=Channel.CUSTOMER, start_ms=0, end_ms=1,
                      detector=Detector.NAME_CUE, confidence=1.5)


def test_drop_reason_must_be_enum():
    b = builder()
    with pytest.raises(LogFieldError):
        b.drop("customer mentioned cancer")
    b.drop(DropReason.SPECIAL_CATEGORY)
    assert json.loads(b.build().to_json())["drop_reason"] == "special_category"


def test_error_records_class_only_never_message():
    b = builder()
    try:
        raise ValueError("card 4111111111111111 for Laura Gómez")
    except ValueError as exc:
        b.error(exc)
    out = b.build().to_json()
    d = json.loads(out)
    assert d["error_class"] == "ValueError" and d["decision"] == "dropped" and d["drop_reason"] == "stage_error"
    assert "4111" not in out and "Laura" not in out


def test_unknown_exception_class_recorded_as_other():
    class LauraGomezError(Exception):
        pass

    b = builder()
    b.error(LauraGomezError("x"))
    assert json.loads(b.build().to_json())["error_class"] == "OtherError"


def test_no_field_can_hold_a_filename_or_text():
    banned = {"file", "filename", "path", "text", "note", "message", "comment", "transcript", "name", "word"}
    for f in dataclasses.fields(CallLog):
        assert not banned & set(f.name.split("_")), f.name
