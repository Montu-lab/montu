"""The BPO's private lexicon (brands, products, agent roster). Held in the BPO's environment only.
Hits are logged as a category; the matched text is never logged."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Lexicon:
    brands: tuple[str, ...] = ()
    products: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    present: bool = field(default=False)

    @staticmethod
    def empty() -> "Lexicon":
        return Lexicon()


def load_lexicon(path: Path | None) -> Lexicon:
    raise NotImplementedError
