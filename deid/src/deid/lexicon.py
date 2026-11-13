"""The BPO's private lexicon (brands, products, agent roster). Held in the BPO's environment only.
Hits are logged as a category; the matched text is never logged."""
from __future__ import annotations

import tomllib
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
    if path is None or not Path(path).exists():
        return Lexicon.empty()
    d = tomllib.loads(Path(path).read_text())
    if set(d) - {"brands", "products", "names"}:
        raise ValueError("lexicon keys must be brands, products, names")
    return Lexicon(tuple(d.get("brands", ())), tuple(d.get("products", ())), tuple(d.get("names", ())), True)
