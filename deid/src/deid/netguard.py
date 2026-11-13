"""Refuse every non-local socket connection in this process. The container's network namespace
(--network none) is the real control; this turns an accidental call into a loud failure."""
from __future__ import annotations

import os
import socket

_saved: dict = {}
_ENV = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1"}


class NetworkBlocked(OSError):
    pass


def _refuse(*_a, **_k):
    raise NetworkBlocked("network access is disabled in deid")


def _guard(orig):
    def connect(self, *a, **k):
        if self.family == socket.AF_UNIX:
            return orig(self, *a, **k)
        raise NetworkBlocked("network access is disabled in deid")
    return connect


def install() -> None:
    if _saved:
        return
    _saved["connect"] = socket.socket.connect
    _saved["connect_ex"] = socket.socket.connect_ex
    _saved["getaddrinfo"] = socket.getaddrinfo
    _saved["create_connection"] = socket.create_connection
    _saved["env"] = {k: os.environ.get(k) for k in _ENV}
    socket.socket.connect = _guard(_saved["connect"])
    socket.socket.connect_ex = _guard(_saved["connect_ex"])
    socket.getaddrinfo = _refuse
    socket.create_connection = _refuse
    os.environ.update(_ENV)


def uninstall() -> None:
    if not _saved:
        return
    socket.socket.connect = _saved["connect"]
    socket.socket.connect_ex = _saved["connect_ex"]
    socket.getaddrinfo = _saved["getaddrinfo"]
    socket.create_connection = _saved["create_connection"]
    for k, v in _saved["env"].items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _saved.clear()
