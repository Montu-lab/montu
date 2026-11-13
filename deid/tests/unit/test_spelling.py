"""UNIT. Letter-by-letter spelling. Expected values written by hand."""
from deid.spelling import SpelledRun, find_spelled_runs


def sp(text, lang):
    return find_spelled_runs(text.split(), lang)


def test_es_letter_names():
    assert sp("eme a erre i a", "es") == [SpelledRun("MARIA", 0, 4)]


def test_es_letter_names_with_as_in_word():
    # "ge de gato" = G; the example word is part of the run
    assert sp("ge de gato o eme e zeta", "es") == [SpelledRun("GOMEZ", 0, 6)]


def test_es_single_letters():
    assert sp("se escribe p e r e z", "es") == [SpelledRun("PEREZ", 2, 6)]


def test_es_preposition_a_is_not_a_run():
    assert sp("voy a casa", "es") == []


def test_en_nato_and_as_in():
    assert sp("m as in mike a r i a", "en") == [SpelledRun("MARIA", 0, 7)]
    assert sp("s m i t h", "en") == [SpelledRun("SMITH", 0, 4)]


def test_en_pronoun_i_is_not_a_run():
    assert sp("i am calling about a bill", "en") == []


def test_short_runs_ignored():
    assert sp("b c", "en") == []
