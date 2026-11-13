"""UNIT. Spoken numbers to digits, with word provenance. Expected values written by hand."""
from deid.numbers import NumberRun, find_number_runs


def runs(text, lang):
    return find_number_runs(text.split(), lang)


def test_es_digit_by_digit():
    assert runs("cuatro cinco dos uno", "es") == [NumberRun("4521", 0, 3)]


def test_es_grouped():
    assert runs("cuarenta y cinco veintiuno", "es") == [NumberRun("4521", 0, 3)]


def test_es_accents_and_compounds():
    assert runs("veintitrés", "es") == [NumberRun("23", 0, 0)]
    assert runs("veintitres", "es") == [NumberRun("23", 0, 0)]


def test_es_hundreds_thousands():
    assert runs("ciento veinte", "es") == [NumberRun("120", 0, 1)]
    assert runs("dos mil veinticuatro", "es") == [NumberRun("2024", 0, 2)]


def test_es_doble_triple():
    assert runs("doble cinco tres", "es") == [NumberRun("553", 0, 2)]
    assert runs("triple cero", "es") == [NumberRun("000", 0, 1)]


def test_es_provenance_inside_sentence():
    assert runs("mi número es seis uno dos", "es") == [NumberRun("612", 3, 5)]


def test_es_fillers_do_not_break_a_run():
    assert runs("cuatro eh cinco dos", "es") == [NumberRun("452", 0, 3)]


def test_non_number_word_breaks_a_run():
    assert runs("uno dos hola tres cuatro", "es") == [NumberRun("12", 0, 1), NumberRun("34", 3, 4)]


def test_y_only_joins_inside_a_group():
    # "y" followed by a non-number is not part of the run
    assert runs("cinco y luego seis", "es") == [NumberRun("5", 0, 0), NumberRun("6", 3, 3)]


def test_mixed_digits_and_words():
    assert runs("4 cinco 2 1", "es") == [NumberRun("4521", 0, 3)]
    assert runs("4521 seis", "es") == [NumberRun("45216", 0, 1)]


def test_digit_tokens_with_punctuation():
    assert runs("es el 4111-1111, gracias", "es") == [NumberRun("41111111", 2, 2)]


def test_en_digit_by_digit_and_oh():
    assert runs("four five two one", "en") == [NumberRun("4521", 0, 3)]
    assert runs("oh seven", "en") == [NumberRun("07", 0, 1)]


def test_en_grouped_and_years():
    assert runs("forty five twenty one", "en") == [NumberRun("4521", 0, 3)]
    assert runs("nineteen eighty five", "en") == [NumberRun("1985", 0, 2)]


def test_en_double_triple():
    assert runs("double five three", "en") == [NumberRun("553", 0, 2)]
    assert runs("triple zero", "en") == [NumberRun("000", 0, 1)]


def test_en_fillers():
    assert runs("four um five two", "en") == [NumberRun("452", 0, 3)]


def test_en_a_and_i_are_not_numbers():
    assert runs("i have a question", "en") == []
