"""Spoken numbers -> digit strings, with exact word-index provenance.

A run is a maximal sequence of number tokens (words, digits, doble/triple, fillers between numbers).
Inside a run, tokens are parsed into groups ("cuarenta y cinco" = 45, "dos mil veinticuatro" = 2024);
consecutive groups are concatenated as digit strings ("cuarenta y cinco veintiuno" = "4521"), which is how
people read card, phone and account numbers aloud. Ambiguity is resolved toward producing digits.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .textnorm import norm

_ES_UNITS = {"cero": 0, "uno": 1, "una": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
             "siete": 7, "ocho": 8, "nueve": 9}
_ES_TEENS = {"diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16,
             "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21, "veintiun": 21,
             "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
             "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29}
_ES_TENS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
            "noventa": 90}
_ES_HUNDREDS = {"cien": 100, "ciento": 100, "doscientos": 200, "doscientas": 200, "trescientos": 300,
                "trescientas": 300, "cuatrocientos": 400, "cuatrocientas": 400, "quinientos": 500,
                "quinientas": 500, "seiscientos": 600, "seiscientas": 600, "setecientos": 700, "setecientas": 700,
                "ochocientos": 800, "ochocientas": 800, "novecientos": 900, "novecientas": 900}
_ES_MULT = {"mil": 1000, "millon": 1_000_000, "millones": 1_000_000}
_ES_REPEAT = {"doble": 2, "triple": 3}
_ES_FILLERS = {"eh", "ehh", "em", "emm", "mm", "mmm", "este", "pues"}
_ES_JOIN = {"y"}

_EN_UNITS = {"zero": 0, "oh": 0, "o": 0, "nought": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9}
_EN_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
             "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
            "ninety": 90}
_EN_MULT = {"thousand": 1000, "million": 1_000_000}
_EN_REPEAT = {"double": 2, "triple": 3}
_EN_FILLERS = {"um", "uh", "er", "erm", "hmm", "mm", "ah"}
_EN_JOIN = {"and"}
_EN_WEAK_ZERO = {"oh", "o"}  # zero only next to another number token

LANGS = {
    "es": dict(units=_ES_UNITS, teens=_ES_TEENS, tens=_ES_TENS, hundreds=_ES_HUNDREDS, hundred_mult=set(),
               mult=_ES_MULT, repeat=_ES_REPEAT, fillers=_ES_FILLERS, join=_ES_JOIN, weak=set()),
    "en": dict(units=_EN_UNITS, teens=_EN_TEENS, tens=_EN_TENS, hundreds={}, hundred_mult={"hundred"},
               mult=_EN_MULT, repeat=_EN_REPEAT, fillers=_EN_FILLERS, join=_EN_JOIN, weak=_EN_WEAK_ZERO),
}


@dataclass(frozen=True)
class NumberRun:
    digits: str
    start: int  # inclusive word index
    end: int  # inclusive word index
    char_words: tuple[int, ...] = field(default=(), compare=False)  # word index of each digit


def _digit_token(tok: str) -> str | None:
    t = re.sub(r"[\s,.\-/]", "", tok.strip().rstrip(",.;:!?"))
    return t if t.isdigit() else None


class _Group:
    """One spoken number being assembled: value = millions + thousands + hundreds + tens + units."""

    def __init__(self):
        self.big = 0  # completed thousands/millions part
        self.hund = 0
        self.tens = 0
        self.units = -1  # -1 = empty
        self.words: list[int] = []
        self.empty = True

    def small(self) -> int:
        return self.hund + self.tens + max(self.units, 0)

    def value(self) -> int:
        return self.big + self.small()


class _Parser:
    def __init__(self, lang: str):
        self.L = LANGS[lang]
        self.digits: list[str] = []
        self.char_words: list[int] = []
        self.g = _Group()
        self.last_kind = None

    def flush(self):
        if not self.g.empty:
            s = str(self.g.value())
            self.digits.append(s)
            # provenance: spread the group's digits over its words, last word takes the remainder
            ws = self.g.words
            for k in range(len(s)):
                self.char_words.append(ws[min(k * len(ws) // len(s), len(ws) - 1)])
        self.g = _Group()

    def literal(self, s: str, idx: int):
        self.flush()
        self.digits.append(s)
        self.char_words.extend([idx] * len(s))

    def add(self, kind: str, val: int, idx: int):
        g = self.g
        if kind == "unit":
            can = (not g.empty and g.units < 0 and (g.tens > 0 or g.hund > 0 or (g.big > 0 and g.small() == 0))
                   and self.last_kind in ("tens", "hund", "mult", "join", "hundmul"))
            if not can:
                self.flush()
                g = self.g
            g.units = val
        elif kind == "teen":
            can = not g.empty and g.tens == 0 and g.units < 0 and (g.hund > 0 or g.big > 0) and \
                self.last_kind in ("hund", "mult", "join", "hundmul")
            if not can:
                self.flush()
                g = self.g
            g.tens = val
            g.units = -1 if val % 10 == 0 or val < 20 else -1
        elif kind == "tens":
            can = not g.empty and g.tens == 0 and g.units < 0 and (g.hund > 0 or g.big > 0) and \
                self.last_kind in ("hund", "mult", "join", "hundmul")
            if not can:
                self.flush()
                g = self.g
            g.tens = val
        elif kind == "hund":
            can = not g.empty and g.small() == 0 and g.big > 0 and self.last_kind in ("mult", "join")
            if not can:
                self.flush()
                g = self.g
            g.hund = val
        elif kind == "hundmul":  # English "hundred"
            if not g.empty and g.hund == 0 and g.tens == 0 and g.units > 0:
                g.hund, g.units = g.units * 100, -1
            else:
                self.flush()
                g = self.g
                g.hund = 100
        elif kind == "mult":
            if not g.empty and g.big == 0 or (not g.empty and g.small() > 0 and g.big >= val * 1000):
                g.big += (g.small() or 1) * val
                g.hund, g.tens, g.units = 0, 0, -1
            else:
                self.flush()
                g = self.g
                g.big = val
        g.empty = False
        g.words.append(idx)
        self.last_kind = kind

    def result(self) -> tuple[str, list[int]]:
        self.flush()
        return "".join(self.digits), self.char_words


def _kind(t: str, L: dict) -> tuple[str, int] | None:
    if t in L["units"]:
        return "unit", L["units"][t]
    if t in L["teens"]:
        return "teen", L["teens"][t]
    if t in L["tens"]:
        return "tens", L["tens"][t]
    if t in L["hundreds"]:
        return "hund", L["hundreds"][t]
    if t in L["hundred_mult"]:
        return "hundmul", 100
    if t in L["mult"]:
        return "mult", L["mult"][t]
    return None


def find_number_runs(words: list[str], lang: str) -> list[NumberRun]:
    L = LANGS.get(lang, LANGS["en"])
    n = len(words)
    toks = [norm(w) for w in words]

    def is_num(i: int) -> bool:
        if i < 0 or i >= n:
            return False
        if _digit_token(words[i]) is not None:
            return True
        t = toks[i]
        if t in L["weak"]:
            return False
        if t in L["repeat"]:
            return i + 1 < n and (_kind(toks[i + 1], L) or (_digit_token(words[i + 1]) or "")[:1]) is not None
        return _kind(t, L) is not None

    def strong_or_weak(i: int) -> bool:
        if is_num(i):
            return True
        if 0 <= i < n and toks[i] in L["weak"]:
            return is_num(i - 1) or is_num(i + 1) or (i + 1 < n and toks[i + 1] in L["weak"] and is_num(i + 2))
        return False

    runs: list[NumberRun] = []
    i = 0
    while i < n:
        if not strong_or_weak(i):
            i += 1
            continue
        p = _Parser(lang if lang in LANGS else "en")
        start = i
        end = i
        j = i
        while j < n:
            t = toks[j]
            d = _digit_token(words[j])
            if d is not None:
                p.literal(d, j)
                end = j
                j += 1
                continue
            if t in L["repeat"] and j + 1 < n:
                nd = _digit_token(words[j + 1])
                k = _kind(toks[j + 1], L)
                if nd is not None and len(nd) == 1:
                    p.literal(nd * L["repeat"][t], j)
                elif k and k[0] == "unit":
                    p.literal(str(k[1]) * L["repeat"][t], j)
                else:
                    break
                p.char_words[-L["repeat"][t]:] = [j + 1] * L["repeat"][t]
                end = j + 1
                j += 2
                continue
            if t in L["weak"] and strong_or_weak(j):
                p.add("unit", 0, j)
                end = j
                j += 1
                continue
            k = _kind(t, L)
            if k:
                p.add(k[0], k[1], j)
                end = j
                j += 1
                continue
            if t in L["join"] and strong_or_weak(j + 1):
                p.last_kind = "join"
                j += 1
                continue
            if t in L["fillers"]:
                f = j
                while f < n and toks[f] in L["fillers"] and f - j < 2:
                    f += 1
                if strong_or_weak(f):
                    j = f
                    continue
            break
        digits, cw = p.result()
        if digits:
            runs.append(NumberRun(digits, start, end, tuple(cw)))
        i = max(end + 1, j if j > start else start + 1)
    return runs
