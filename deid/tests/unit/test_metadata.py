"""UNIT. Batch metadata is an allow-list."""
import pytest

from deid.metadata import MetadataRejected, parse_batch_metadata

OK = {"profile_code": "ES-GENERIC-es-S2", "channel_map": {"agent": 0, "customer": 1}}


def reason(policy, raw):
    with pytest.raises(MetadataRejected) as e:
        parse_batch_metadata(raw, policy)
    return e.value.reason


def test_minimal_accepted(policy):
    m = parse_batch_metadata(OK, policy)
    assert m.profile_code == "ES-GENERIC-es-S2" and m.channel_map == {"agent": 0, "customer": 1}


@pytest.mark.parametrize("key", ["client_name", "client", "brand", "customer_id", "campaign", "notes", "x"])
def test_any_extra_key_rejects_the_batch(policy, key):
    assert reason(policy, {**OK, key: "Movistela"}) == "unknown_key"


def test_rejection_message_does_not_repeat_the_value(policy):
    with pytest.raises(MetadataRejected) as e:
        parse_batch_metadata({**OK, "client_name": "Movistela"}, policy)
    assert "Movistela" not in str(e.value)


def test_missing_profile(policy):
    assert reason(policy, {"channel_map": {"agent": 0, "customer": 1}}) == "missing_key"


def test_unknown_profile(policy):
    assert reason(policy, {**OK, "profile_code": "ES-GENERIC-es-S9"}) == "unknown_profile"


@pytest.mark.parametrize("cm", [{"agent": 0}, {"agent": 0, "customer": 0}, {"agent": 0, "customer": 2},
                                {"agent": 0, "customer": 1, "supervisor": 2}])
def test_bad_channel_map(policy, cm):
    assert reason(policy, {**OK, "channel_map": cm}) == "bad_channel_map"
