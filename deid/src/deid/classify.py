"""Call-level exclusion: decides whether a call is dropped. Runs before anything is written.

Day-1 mechanism: lexicons from policies/ plus deterministic PCI and age rules. Recall-first: it over-drops.
"""
from __future__ import annotations

from .numbers import find_number_runs
from .policy import Profile
from .textnorm import find_phrase, is_placeholder, norm, phrase_tokens
from .types import TRIGGER_TO_REASON, Category, Channel, Decision, Detector, Entity, Word

PCI_WINDOW = 8
_AGE_PREFIX = {"es": {"tengo", "tiene", "tienes", "tienen", "tenemos", "cumple", "cumplio", "cumplira", "cumplir",
                      "cumplo"},
               "en": set()}
_AGE_SUFFIX = {"es": [["anos"], ["ano"], ["anitos"]],
               "en": [["years", "old"], ["year", "old"], ["yrs", "old"], ["yo"]]}


def _toks(words: list[Word]) -> list[str]:
    return [norm(w.text) if not is_placeholder(w.text) else "|" for w in words]


def _lev(a: str, b: str, cap: int) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


FUZZY_MIN_LEN = 8  # below this, edit distance confuses ordinary words ("cancel" / "cancer")


def _has_phrase(toks: list[str], phrases) -> bool:
    """Exact phrase match; single long terms also match ASR misspellings (edit distance 1, or 2 from 12 letters)."""
    for p in phrases:
        pt = phrase_tokens(p)
        if find_phrase(toks, pt):
            return True
        if len(pt) == 1 and len(pt[0]) >= FUZZY_MIN_LEN:
            cap = 2 if len(pt[0]) >= 12 else 1
            if any(len(t) >= FUZZY_MIN_LEN - 1 and _lev(t, pt[0], cap) <= cap for t in toks):
                return True
    return False


def _pci(words: list[Word], toks: list[str], entities: list[Entity], cues) -> bool:
    if any(e.category == Category.CARD or e.detector == Detector.LUHN for e in entities):
        return True
    raw = [w.text if not is_placeholder(w.text) else "|" for w in words]
    for lang in ("es", "en"):
        runs = [r for r in find_number_runs(raw, lang) if len(r.digits) >= 3]
        for p in cues:
            pt = phrase_tokens(p)
            for i in find_phrase(toks, pt):
                ce = i + len(pt) - 1
                if any((r.start > ce and r.start - ce <= PCI_WINDOW) or (r.end < i and i - r.end <= 4) for r in runs):
                    return True
    return False


CARD_RUN_MIN = 12


def _card_word_and_long_run(all_words: dict, cards) -> bool:
    """Fail-closed PCI rule: a card word anywhere in the call and any 12+ digit run that is not a valid CLABE."""
    from .detect.checksums import clabe_valid
    if not any(_has_phrase(_toks(ws), cards) for ws in all_words.values()):
        return False
    for ws in all_words.values():
        raw = [w.text if not is_placeholder(w.text) else "|" for w in ws]
        for lang in ("es", "en"):
            for r in find_number_runs(raw, lang):
                if len(r.digits) >= CARD_RUN_MIN and not (len(r.digits) == 18 and clabe_valid(r.digits)):
                    return True
    return False


def _minor_age(raw: list[str], toks: list[str], lang: str) -> bool:
    for r in find_number_runs(raw, lang):
        try:
            age = int(r.digits)
        except ValueError:
            continue
        if not 0 < age < 18:
            continue
        after = toks[r.end + 1:r.end + 3]
        if not any(after[:len(s)] == s for s in _AGE_SUFFIX.get(lang, [])):
            continue
        if lang == "es" and (r.start == 0 or toks[r.start - 1] not in _AGE_PREFIX["es"]):
            continue
        return True
    return False


def classify_call(words: dict[Channel, list[Word]], entities: list[Entity], profile: Profile,
                  lang: str) -> Decision:
    langs = [lang] + [x for x in profile.languages if x != lang]
    fired: set[str] = set()
    for ch, ws in words.items():
        toks = _toks(ws)
        raw = [w.text if not is_placeholder(w.text) else "|" for w in ws]
        for lg in langs:
            lex = profile.lexicons.get(lg, {})
            if _pci(ws, toks, [e for e in entities if e.channel == ch], lex.get("pci_cue", ())):
                fired.add("pci")
            if _has_phrase(toks, lex.get("special_category", ())):
                fired.add("special_category")
            if _has_phrase(toks, lex.get("minor", ())) or _minor_age(raw, toks, lg):
                fired.add("minor")
            if _has_phrase(toks, lex.get("vulnerable", ())):
                fired.add("vulnerable")
    for lg in langs:
        if _card_word_and_long_run(words, profile.lexicons.get(lg, {}).get("card_word", ())):
            fired.add("pci")
    rules = [r for r in profile.rules if r.trigger in fired]
    reasons = []
    for r in rules:
        reason = TRIGGER_TO_REASON[r.trigger]
        if reason not in reasons:
            reasons.append(reason)
    return Decision(bool(rules), tuple(reasons), tuple(r.id for r in rules))
