"""What the Montu operator may read: out/logs and out/released. A convenience, not a control:
the control is the BPO's IAM on those prefixes (plan §4)."""
from __future__ import annotations

from pathlib import Path

ALLOWED = ("logs", "released")


class AccessRefused(Exception):
    pass


class MontuView:
    def __init__(self, out_root: Path):
        self.root = Path(out_root).resolve()
        self.allowed = [self.root / a for a in ALLOWED]

    def _check(self, p: Path) -> Path:
        r = p.resolve()  # follows symlinks
        if not any(r == a or a in r.parents for a in self.allowed):
            raise AccessRefused("outside logs/ and released/")
        return r

    def read(self, rel_path: str) -> bytes:
        if Path(rel_path).is_absolute():
            raise AccessRefused("absolute path")
        return self._check(self.root / rel_path).read_bytes()

    def list(self) -> list[str]:
        out = []
        for a in self.allowed:
            if a.is_dir():
                for p in sorted(a.rglob("*")):
                    try:
                        if p.is_file() and self._check(p):
                            out.append(str(p.relative_to(self.root)))
                    except AccessRefused:
                        continue
        return out
