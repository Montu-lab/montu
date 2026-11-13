"""UNIT. No network: the in-process guard, a static scan of the package source, and the ASR
loader's refusal of hub ids. The container's --network none is the real control and is not
tested here (it is a property of how the BPO runs the image)."""
import ast
import socket
from pathlib import Path

import pytest

from deid import netguard

SRC = Path(__file__).resolve().parents[2] / "src" / "deid"

FORBIDDEN = {"requests", "urllib", "urllib3", "http.client", "httpx", "aiohttp", "boto3", "botocore",
             "google.cloud", "azure", "ftplib", "smtplib", "paramiko", "websocket", "websockets", "grpc"}
# Modules allowed to import socket/http.server, and why.
ALLOWED = {
    "netguard.py": {"socket"},          # the guard itself
    "review_app.py": {"http.server",    # binds 127.0.0.1 for the BPO reviewer; never connects out
                      "urllib.parse"},  # string parsing of the request path/form; no I/O
}


def test_guard_refuses_tcp_connect():
    netguard.install()
    try:
        with pytest.raises(netguard.NetworkBlocked):
            socket.create_connection(("127.0.0.1", 9), timeout=1)
        with pytest.raises(netguard.NetworkBlocked):
            socket.getaddrinfo("example.com", 443)
    finally:
        netguard.uninstall()


def test_guard_allows_unix_sockets(tmp_path):
    netguard.install()
    try:
        a, b = socket.socketpair(socket.AF_UNIX)
        a.sendall(b"x")
        assert b.recv(1) == b"x"
    finally:
        netguard.uninstall()


def test_guard_sets_offline_env():
    import os
    netguard.install()
    try:
        assert os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("TRANSFORMERS_OFFLINE") == "1"
    finally:
        netguard.uninstall()


def _imports(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


def test_no_network_imports_in_package():
    bad = []
    for p in SRC.rglob("*.py"):
        for mod in _imports(p):
            allowed = ALLOWED.get(p.name, set())
            if mod in allowed:
                continue
            if mod == "socket" or mod.startswith("http.") or any(
                    mod == f or mod.startswith(f + ".") for f in FORBIDDEN):
                bad.append(f"{p.relative_to(SRC)}: {mod}")
    assert bad == []


def test_asr_refuses_hub_id():
    from deid.asr import FasterWhisperTranscriber
    with pytest.raises(ValueError) as e:
        FasterWhisperTranscriber("Systran/faster-whisper-small")
    assert "local directory" in str(e.value)
