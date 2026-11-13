"""Letter-by-letter spelling -> letters, with word-index provenance.

Recognises single-letter tokens, letter names ("eme", "erre", "aitch"), the NATO alphabet, and the
"X de <word>" / "X as in <word>" / "X for <word>" disambiguation forms. Tokens that are also ordinary
words ("a", "i", "o", "e", "y") count as letters only inside a run of at least `min_letters`.
"""
from __future__ import annotations

from dataclasses import dataclass

from .textnorm import norm

_ES = {"a": "A", "be": "B", "ce": "C", "de": "D", "e": "E", "efe": "F", "ge": "G", "hache": "H", "i": "I",
       "jota": "J", "ka": "K", "ele": "L", "eme": "M", "ene": "N", "ene~": "N", "o": "O", "pe": "P",
       "cu": "Q", "erre": "R", "ere": "R", "ese": "S", "te": "T", "u": "U", "uve": "V", "ve": "V",
       "equis": "X", "zeta": "Z", "zeda": "Z", "ye": "Y"}
_ES_MULTI = {("uve", "doble"): "W", ("doble", "uve"): "W", ("i", "griega"): "Y", ("be", "larga"): "B",
             ("ve", "corta"): "V", ("ve", "chica"): "V", ("be", "grande"): "B"}
_ES_DISAMBIG = [("de",), ("como",), ("de", "la"), ("del",)]

_EN = {"bee": "B", "cee": "C", "see": "C", "dee": "D", "ee": "E", "eff": "F", "gee": "G", "aitch": "H",
       "jay": "J", "kay": "K", "el": "L", "em": "M", "en": "N", "pee": "P", "cue": "Q", "queue": "Q",
       "ar": "R", "ess": "S", "tee": "T", "vee": "V", "ex": "X", "why": "Y", "zee": "Z", "zed": "Z"}
_NATO = {"alpha": "A", "alfa": "A", "bravo": "B", "charlie": "C", "delta": "D", "echo": "E", "foxtrot": "F",
         "golf": "G", "hotel": "H", "india": "I", "juliet": "J", "juliett": "J", "kilo": "K", "lima": "L",
         "mike": "M", "november": "N", "oscar": "O", "papa": "P", "quebec": "Q", "romeo": "R", "sierra": "S",
         "tango": "T", "uniform": "U", "victor": "V", "whiskey": "W", "whisky": "W", "xray": "X",
         "x-ray": "X", "yankee": "Y", "zulu": "Z"}
_EN_MULTI = {("double", "u"): "W", ("double", "you"): "W"}
_EN_DISAMBIG = [("as", "in"), ("for",), ("like",)]

# Letters that are also everyday words: they extend a run but never start a run on their own unless
# followed by a non-ambiguous letter.
_AMBIG = {"es": {"a", "e", "o", "u", "de", "te", "ve", "ese", "ye", "i"},
          "en": {"a", "i", "o", "u", "el", "en", "ex", "see", "why", "you", "em", "ar"}}


@dataclass(frozen=True)
class SpelledRun:
    letters: str
    start: int
    end: int


def _letter_at(toks: list[str], i: int, lang: str) -> tuple[str, int] | None:
    """(letter, tokens consumed) for a letter starting at i, including any disambiguation tail."""
    n = len(toks)
    t = toks[i]
    multi = _ES_MULTI if lang == "es" else _EN_MULTI
    if i + 1 < n and (t, toks[i + 1]) in multi:
        return multi[(t, toks[i + 1])], 2
    letter = None
    if len(t) == 1 and t.isalpha():
        letter = t.upper()
    elif lang == "es" and t in _ES:
        letter = _ES[t]
    elif lang != "es" and t in _EN:
        letter = _EN[t]
    elif t in _NATO:
        return _NATO[t], 1
    if letter is None:
        return None
    # "ge de gato", "m as in mike": consume the cue and the example word if it starts with the letter
    for cue in (_ES_DISAMBIG if lang == "es" else _EN_DISAMBIG):
        k = len(cue)
        if i + k + 1 < n and tuple(toks[i + 1:i + 1 + k]) == cue:
            ex = toks[i + 1 + k]
            if ex[:1].upper() == letter or _NATO.get(ex) == letter:
                return letter, k + 2
    return letter, 1


def find_spelled_runs(words: list[str], lang: str, min_letters: int = 3) -> list[SpelledRun]:
    toks = [norm(w) for w in words]
    amb = _AMBIG.get(lang, _AMBIG["en"])
    runs: list[SpelledRun] = []
    i, n = 0, len(toks)
    while i < n:
        first = _letter_at(toks, i, lang)
        if first is None:
            i += 1
            continue
        letters, j, strong = [], i, 0
        while j < n:
            got = _letter_at(toks, j, lang)
            if got is None:
                break
            letters.append(got[0])
            if toks[j] not in amb or got[1] > 1:
                strong += 1
            j += got[1]
        if len(letters) >= min_letters and strong >= 1:
            runs.append(SpelledRun("".join(letters), i, j - 1))
            i = j
        else:
            i += 1
    return runs
