"""UNIT. Exclusion decisions against the SHIPPED policy files (policies/), not fixtures.
Says nothing about the classifier's precision or recall on real calls."""
from deid.classify import classify_call
from deid.detect.detectors import detect_channel
from deid.lexicon import Lexicon
from deid.types import Channel, DropReason

from conftest import mkwords


def decide(policy, customer, agent="buenos días en qué puedo ayudarle", code="ES-GENERIC-es-S2", lang="es"):
    profile = policy.profile(code)
    words = {Channel.AGENT: mkwords(agent, Channel.AGENT), Channel.CUSTOMER: mkwords(customer)}
    entities = [e for ch, w in words.items() for e in detect_channel(w, lang, ch, Lexicon.empty())]
    return classify_call(words, entities, profile, lang)


def test_card_number_drops(policy):
    d = decide(policy, "es la cuatro uno uno uno uno uno uno uno uno uno uno uno uno uno uno uno")
    assert d.drop and DropReason.PCI in d.reasons


def test_cvv_cue_drops(policy):
    d = decide(policy, "el código de seguridad es uno dos tres")
    assert d.drop and DropReason.PCI in d.reasons


def test_card_read_back_by_agent_drops(policy):
    d = decide(policy, "sí", agent="le confirmo la tarjeta 4111 1111 1111 1111")
    assert d.drop and DropReason.PCI in d.reasons


def test_health_drops(policy):
    d = decide(policy, "es que estoy con quimioterapia y no puedo ir")
    assert d.drop and DropReason.SPECIAL_CATEGORY in d.reasons


def test_religion_drops(policy):
    d = decide(policy, "soy musulmán y quería saber")
    assert d.drop and DropReason.SPECIAL_CATEGORY in d.reasons


def test_minor_cue_drops(policy):
    d = decide(policy, "la línea es de mi hija")
    assert d.drop and DropReason.MINOR in d.reasons


def test_minor_age_drops(policy):
    d = decide(policy, "el titular tiene doce años")
    assert d.drop and DropReason.MINOR in d.reasons


def test_adult_age_does_not_trigger_minor(policy):
    d = decide(policy, "tengo cuarenta años y quiero cambiar de tarifa")
    assert DropReason.MINOR not in d.reasons


def test_vulnerable_drops(policy):
    d = decide(policy, "me he quedado sin trabajo y no puedo pagar")
    assert d.drop and DropReason.VULNERABLE in d.reasons


def test_bereavement_drops_en(policy):
    d = decide(policy, "my husband passed away last month", agent="how can I help", code="US-GENERIC-en-S2",
               lang="en")
    assert d.drop and DropReason.VULNERABLE in d.reasons


def test_neutral_call_kept(policy):
    d = decide(policy, "quería cambiar mi tarifa de datos a una más barata")
    assert not d.drop and d.reasons == ()


def test_card_mentioned_without_digits_kept(policy):
    d = decide(policy, "ya me llegó la tarjeta nueva gracias")
    assert not d.drop


def test_rule_ids_recorded(policy):
    d = decide(policy, "el código de seguridad es uno dos tres")
    assert "ES-PCI-1" in d.rule_ids


def test_todo_rules_do_not_run(policy):
    p = policy.profile("ES-GENERIC-es-S2")
    assert "ES-LOPDGDD-ART9" not in {r.id for r in p.rules}
    assert "ES-LOPDGDD-ART9" in {r.id for r in p.todo_rules}
