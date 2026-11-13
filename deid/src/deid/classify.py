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


def _has_phrase(toks: list[str], phrases) -> bool:
    return any(find_phrase(toks, phrase_tokens(p)) for p in phrases)


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
    rules = [r for r in profile.rules if r.trigger in fired]
    reasons = []
    for r in rules:
        reason = TRIGGER_TO_REASON[r.trigger]
        if reason not in reasons:
            reasons.append(reason)
    return Decision(bool(rules), tuple(reasons), tuple(r.id for r in rules))
