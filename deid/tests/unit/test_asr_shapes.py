"""UNIT. Shapes seen in real faster-whisper output on synthetic telephony audio (smoke run, 2026-11-13,
whisper-small int8, CPU). The strings are paraphrased shapes, not copied call content: no real data exists."""
from deid.classify import classify_call
from deid.detect.detectors import detect_channel
from deid.lexicon import Lexicon
from deid.types import Category, Channel, DropReason

from conftest import mkwords


def ents(text, lang, channel=Channel.CUSTOMER):
    w = mkwords(text, channel)
    return detect_channel(w, lang, channel, Lexicon.empty())


def covers(es, cat, s, e):
    return any(x.category == cat and x.word_start <= s and x.word_end >= e for x in es)


def test_card_with_lost_digits_still_drops_when_a_card_is_mentioned(policy):
    # the ASR lost digits, so no Luhn-valid run exists; a card word plus a long digit run must still drop
    agent = mkwords("con qué tarjeta quiere pagar", Channel.AGENT)
    cust = mkwords("con esta 249 -2589 -339 -4491")
    words = {Channel.AGENT: agent, Channel.CUSTOMER: cust}
    es = detect_channel(agent, "es", Channel.AGENT, Lexicon.empty()) + \
        detect_channel(cust, "es", Channel.CUSTOMER, Lexicon.empty())
    d = classify_call(words, es, policy.profile("ES-GENERIC-es-S2"), "es")
    assert d.drop and DropReason.PCI in d.reasons


def test_long_run_without_card_word_does_not_trigger_pci(policy):
    cust = mkwords("mi referencia es 249 -2589 -339 -4491")
    words = {Channel.AGENT: mkwords("dígame", Channel.AGENT), Channel.CUSTOMER: cust}
    es = detect_channel(cust, "es", Channel.CUSTOMER, Lexicon.empty())
    d = classify_call(words, es, policy.profile("ES-GENERIC-es-S2"), "es")
    assert DropReason.PCI not in d.reasons


def test_glued_spoken_email_es():
    assert covers(ents("es rodrigoarrobalimei .com gracias", "es"), Category.EMAIL, 1, 2)


def test_glued_email_with_www():
    assert covers(ents("sí www .drivo .islescazarrobaiaov .com vale", "es"), Category.EMAIL, 1, 4)


def test_email_with_glued_domain_en():
    assert covers(ents("it's ashley at outlooks .com thanks", "en"), Category.EMAIL, 1, 4)


def test_brand_slot_survives_asr_sentence_break():
    es = ents("Ashley, thank you for calling. Alright, more often.", "en", Channel.AGENT)
    assert covers(es, Category.BRAND, 5, 7)


def test_brand_slot_es_survives_por():
    es = ents("muy bien gracias por llamar ya por bajo.", "es", Channel.AGENT)
    assert covers(es, Category.BRAND, 5, 7)


def test_vocative_name_without_cue_es():
    es = ents("Muy bien, Pablo, gracias por llamar", "es", Channel.AGENT)
    assert covers(es, Category.NAME, 2, 2)


def test_misheard_name_mid_sentence():
    assert covers(ents("vale, gracias, Ugo, o sea", "es"), Category.NAME, 2, 2)


def test_sentence_initial_capital_is_not_a_name():
    es = ents("Perfecto. Déjeme revisar el sistema.", "es", Channel.AGENT)
    assert not any(x.category == Category.NAME for x in es)


def test_dob_includes_leading_article():
    es = ents("Nací el doce de marzo de mil novecientos ochenta", "es")
    assert covers(es, Category.DOB, 1, 8)


def test_address_plural_cue():
    es = ents("vivo en Colonias Romanos de Quelle Durango, número 4, gracias", "es")
    assert covers(es, Category.ADDRESS, 2, 7)


def test_vocative_before_closing_after_sentence_break_es():
    es = ents("¡Muy bien! Sergio, gracias por llamar", "es", Channel.AGENT)
    assert covers(es, Category.NAME, 2, 2)


def test_vocative_with_exclamation_marks():
    es = ents("¡Muy bien! ¡Deatriz! ¡Gracias por llamar a...", "es", Channel.AGENT)
    assert covers(es, Category.NAME, 2, 2)


def test_vocative_before_closing_en():
    es = ents("All right. Brooke, thank you for calling.", "en", Channel.AGENT)
    assert covers(es, Category.NAME, 2, 2)


def test_short_number_fragment_next_to_a_long_run_is_absorbed():
    es = ents("es las 228 de 1 6 4 6 4 2 8 3 9 vale", "es")
    assert any(x.word_start <= 2 and x.word_end >= 12 for x in es)


def test_address_capitalised_street_name_es():
    es = ents("Vivo en Paseo de Gracia 30, si", "es")
    assert covers(es, Category.ADDRESS, 2, 5)


def test_misspelled_long_special_category_term_drops(policy):
    cust = mkwords("es que estoy con quimiotrapia y no puedo ir")
    words = {Channel.AGENT: mkwords("dígame", Channel.AGENT), Channel.CUSTOMER: cust}
    d = classify_call(words, [], policy.profile("ES-GENERIC-es-S2"), "es")
    assert d.drop and DropReason.SPECIAL_CATEGORY in d.reasons


def test_short_terms_are_not_fuzzy_cancel_is_not_cancer(policy):
    cust = mkwords("I want to cancel my contract")
    words = {Channel.AGENT: mkwords("how can I help", Channel.AGENT), Channel.CUSTOMER: cust}
    d = classify_call(words, [], policy.profile("US-GENERIC-en-S2"), "en")
    assert DropReason.SPECIAL_CATEGORY not in d.reasons


def test_dot_prefixed_fragments_join_the_email():
    es = ents("nací en mayo .esgubo .medina juanarrobagmail .com es", "es")
    assert covers(es, Category.EMAIL, 3, 6)


def test_alnum_fragment_next_to_number_is_absorbed():
    es = ents("es el 1 2 3 4 5 6 7 8 -34F vale", "es")
    assert any(x.word_start <= 2 and x.word_end >= 10 for x in es)


def test_code_token_with_letters_and_digits():
    assert any(x.word_start == 2 for x in ents("es el B12X vale", "es"))
    assert not ents("tengo fibra con 5G en casa", "es")
