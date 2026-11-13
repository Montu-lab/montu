"""Refuse every non-local socket connection in this process. The container's network namespace
(--network none) is the real control; this turns an accidental call into a loud failure."""
from __future__ import annotations


class NetworkBlocked(OSError):
    pass


def install() -> None:
    raise NotImplementedError


def uninstall() -> None:
    raise NotImplementedError
