"""Token normalisation shared by detectors and lexicon matching."""
from __future__ import annotations

import re
import unicodedata

PLACEHOLDER = re.compile(r"^\[[A-Z_]+\]$")
_PUNCT = re.compile(r"[^\w@.\-']+", re.UNICODE)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).replace("ñ", "n")


def norm(tok: str) -> str:
    """lowercase, no accents, no surrounding punctuation, no apostrophes."""
    t = strip_accents(tok.lower()).replace("’", "").replace("'", "")
    t = re.sub(r"[^\w@.\-]", "", t)
    return t.strip(".-")


def ends_clause(tok: str) -> bool:
    return bool(re.search(r"[,.;:!?]$", tok.strip()))


def is_placeholder(tok: str) -> bool:
    return bool(PLACEHOLDER.match(tok))


def phrase_tokens(phrase: str) -> list[str]:
    return [norm(t) for t in phrase.split() if norm(t)]


def find_phrase(ntoks: list[str], phrase: list[str], start: int = 0) -> list[int]:
    """Start indices where `phrase` (normalised tokens) occurs in `ntoks`."""
    n = len(phrase)
    if n == 0:
        return []
    return [i for i in range(start, len(ntoks) - n + 1) if ntoks[i:i + n] == phrase]
