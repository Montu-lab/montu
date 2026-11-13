"""UNIT. Detectors over synthetic word streams. Says nothing about ASR output on real audio,
where words are mis-heard, merged and mis-timed."""
from deid.detect.detectors import detect_channel
from deid.lexicon import Lexicon
from deid.types import Category, Channel, Detector

from conftest import mkwords

CARD_ES = "cuatro uno uno uno uno uno uno uno uno uno uno uno uno uno uno uno"  # 4111111111111111
CARD_EN = "four one one one one one one one one one one one one one one one"


def ents(text, lang, channel=Channel.CUSTOMER, lexicon=Lexicon.empty(), low=None):
    w = mkwords(text, channel, low=low)
    return w, detect_channel(w, lang, channel, lexicon)


def covering(entities, category, start, end):
    return [e for e in entities if e.category == category and e.word_start <= start and e.word_end >= end]


def test_card_spoken_digit_by_digit_es():
    w, e = ents(f"mi tarjeta es la {CARD_ES} gracias", "es")
    hit = covering(e, Category.CARD, 4, 19)
    assert hit and hit[0].detector == Detector.LUHN
    assert hit[0].start_ms == w[4].start_ms and hit[0].end_ms >= w[19].end_ms


def test_card_spoken_en():
    _, e = ents(f"the card is {CARD_EN}", "en")
    assert covering(e, Category.CARD, 3, 18)


def test_card_spoken_in_groups_es():
    # 4111 1111 1111 1111 as "cuarenta y uno once ..." is unusual; groups of four as digits+words
    _, e = ents("es el 4111 1111 1111 1111", "es")
    assert covering(e, Category.CARD, 2, 5)


def test_phone_es():
    _, e = ents("llámame al seis uno dos tres cuatro cinco seis siete ocho", "es")
    assert covering(e, Category.PHONE, 2, 10)


def test_email_spoken_es():
    _, e = ents("mi correo es juan punto perez arroba gmail punto com", "es")
    assert covering(e, Category.EMAIL, 3, 9)


def test_email_spoken_en():
    _, e = ents("it's john dot smith at example dot com thanks", "en")
    assert covering(e, Category.EMAIL, 1, 7)


def test_dni_spoken():
    _, e = ents("mi dni es uno dos tres cuatro cinco seis siete ocho zeta", "es")
    hit = covering(e, Category.NATIONAL_ID, 3, 11)
    assert hit and hit[0].detector == Detector.DNI


def test_clabe_spoken():
    digits = "cero tres dos uno ocho cero cero cero cero uno uno ocho tres cinco nueve siete uno nueve"
    _, e = ents(f"la clabe es {digits}", "es")
    hit = covering(e, Category.ACCOUNT, 3, 20)
    assert hit and hit[0].detector == Detector.CLABE


def test_iban_spoken_es():
    _, e = ents("el iban es ES9121000418450200051332", "es")
    assert covering(e, Category.IBAN, 3, 3)


def test_catch_all_digits_customer():
    _, e = ents("pues es el siete ocho nueve cero", "es")
    hit = covering(e, Category.NUMBER, 3, 6)
    assert hit and hit[0].detector == Detector.CATCH_ALL_DIGITS


def test_catch_all_digits_agent_too():
    # agents read numbers back
    _, e = ents("le confirmo siete ocho nueve cero", "es", channel=Channel.AGENT)
    assert covering(e, Category.NUMBER, 2, 5) or covering(e, Category.REFERENCE, 2, 5)


def test_three_digits_without_cue_kept():
    _, e = ents("son tres euros con veinte", "es")
    assert not [x for x in e if x.category in (Category.NUMBER, Category.CARD, Category.PHONE)]


def test_reference_with_cue():
    _, e = ents("el número de pedido es a b siete ocho", "es")
    assert covering(e, Category.REFERENCE, 5, 8) or covering(e, Category.SPELLED, 5, 8)


def test_spelled_name_is_redacted():
    _, e = ents("mi apellido se escribe ge o eme e zeta", "es")
    assert covering(e, Category.SPELLED, 4, 8) or covering(e, Category.NAME, 4, 8)


def test_brand_and_agent_from_lexicon():
    lex = Lexicon(brands=("Movistela",), products=("Fibra Total",), names=("Carmen",), present=True)
    _, e = ents("bienvenido a movistela le atiende carmen sobre su fibra total", "es",
                channel=Channel.AGENT, lexicon=lex)
    assert covering(e, Category.BRAND, 2, 2)
    assert covering(e, Category.NAME, 5, 5)
    assert covering(e, Category.BRAND, 8, 9)  # products are redacted as BRAND


def test_brand_from_greeting_slot_without_lexicon_es():
    _, e = ents("gracias por llamar a Zentrix Energía, le atiende Laura, ¿en qué puedo ayudarle?", "es",
                channel=Channel.AGENT)
    brand = covering(e, Category.BRAND, 4, 5)
    assert brand and brand[0].detector == Detector.GREETING_SLOT
    assert covering(e, Category.NAME, 8, 8)


def test_brand_from_greeting_slot_without_lexicon_en():
    _, e = ents("thank you for calling Brightwave Mobile, my name is Kevin, how can I help", "en",
                channel=Channel.AGENT)
    assert covering(e, Category.BRAND, 4, 5)
    assert covering(e, Category.NAME, 9, 9)


def test_customer_self_introduction():
    _, e = ents("hola me llamo Ana Beltrán y llamo por la factura", "es")
    assert covering(e, Category.NAME, 3, 4)


def test_dob_with_cue():
    _, e = ents("mi fecha de nacimiento es el doce de marzo de mil novecientos ochenta", "es")
    assert covering(e, Category.DOB, 6, 12)


def test_address_with_cue():
    _, e = ents("vivo en la calle Alcalá número doce", "es")
    assert covering(e, Category.ADDRESS, 3, 6)


def test_low_confidence_neighbour_folded_into_entity():
    text = f"es {CARD_ES} vale"
    # index 17 ("vale") is low confidence, adjacent to the card's last word (16)
    _, e = ents(text, "es", low={17})
    hit = covering(e, Category.CARD, 1, 17)
    assert hit, "a low-confidence word next to an entity must be folded into it"


def test_unclear_run_redacted():
    _, e = ents("bueno pues mira xxx yyy zzz y ya", "es", low={3, 4, 5})
    hit = covering(e, Category.UNCLEAR, 3, 5)
    assert hit and hit[0].detector == Detector.LOW_CONFIDENCE
