"""UNIT. The shipped policy files load; the loader refuses uncited rules and unversioned changes."""
import shutil

import pytest

from deid.policy import PolicyError, load_policy, write_lock

from conftest import POLICY_DIR


def copy(tmp_path):
    d = tmp_path / "policies"
    shutil.copytree(POLICY_DIR, d)
    return d


def test_shipped_policy_loads(policy):
    assert policy.version == "0.1.2"
    assert {"ES-GENERIC-es-S2", "MX-GENERIC-es-S2", "US-GENERIC-en-S2", "US-GENERIC-en-S3"} <= set(policy.profiles)
    assert len(policy.digest) == 64


def test_every_jurisdiction_in_the_brief_has_a_file(policy):
    from pathlib import Path
    assert {p.stem for p in (POLICY_DIR / "jurisdictions").glob("*.toml")} >= {"ES", "MX", "CO", "BR", "AR", "US"}


def test_unknown_profile(policy):
    with pytest.raises(PolicyError) as e:
        policy.profile("ES-GENERIC-es-S9")
    assert e.value.reason == "unknown_profile"


def test_uncited_rule_refused(tmp_path):
    d = copy(tmp_path)
    with open(d / "jurisdictions" / "ES.toml", "a") as f:
        f.write('\n[[rules]]\nid = "ES-X"\ntrigger = "pci"\naction = "drop"\n')
    with pytest.raises(PolicyError) as e:
        load_policy(d)
    assert e.value.reason == "uncited_rule"


def test_unknown_trigger_refused(tmp_path):
    d = copy(tmp_path)
    with open(d / "jurisdictions" / "ES.toml", "a") as f:
        f.write('\n[[rules]]\nid = "ES-X"\ntrigger = "vibes"\naction = "drop"\ncitation = "x"\nverified = false\n')
    with pytest.raises(PolicyError) as e:
        load_policy(d)
    assert e.value.reason == "unknown_trigger"


def test_content_change_without_new_version_refused(tmp_path):
    d = copy(tmp_path)
    p = d / "lexicons" / "es" / "vulnerable.txt"
    p.write_text(p.read_text() + "una frase nueva\n")
    with pytest.raises(PolicyError) as e:
        load_policy(d)
    assert e.value.reason == "lock_mismatch"


def test_lock_tool_refuses_to_rewrite_a_version(tmp_path):
    d = copy(tmp_path)
    p = d / "lexicons" / "es" / "vulnerable.txt"
    p.write_text(p.read_text() + "una frase nueva\n")
    with pytest.raises(PolicyError) as e:
        write_lock(d, load_policy(POLICY_DIR).version)
    assert e.value.reason == "version_exists"


def test_bumped_version_loads(tmp_path):
    d = copy(tmp_path)
    p = d / "lexicons" / "es" / "vulnerable.txt"
    p.write_text(p.read_text() + "una frase nueva\n")
    import re
    (d / "policy.toml").write_text(re.sub(r'version = "[0-9.]+"', 'version = "9.9.9"', (d / "policy.toml").read_text()))
    write_lock(d, "9.9.9")
    assert load_policy(d).version == "9.9.9"


def test_uncited_todo_rules_are_reported(policy):
    mx = policy.profile("MX-GENERIC-es-S2")
    assert {r.id for r in mx.todo_rules} >= {"MX-LFPDPPP-SENSITIVE", "MX-LFPDPPP-MINOR"}
    assert all(r.citation_gap for r in mx.todo_rules)
