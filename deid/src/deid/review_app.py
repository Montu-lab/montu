"""Minimal review tool for the BPO's reviewer. Binds 127.0.0.1 only; reach it through the BPO's own tunnel.

Shows a seeded random sample of staged calls: redacted audio, redacted transcript and the call's log side by side.
The reviewer approves or rejects the batch (the approval binds to the manifest digest). Reason codes go to
out/logs (Montu-readable); free-text notes go to work/ (BPO only) and are never copied to out/.
"""
from __future__ import annotations

import html
import json
import random
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .manifest import manifest_digest
from .release import record_approval

REASONS = ["ok", "identifier_audible", "identifier_in_transcript", "brand_audible", "wrong_channel_map",
           "fill_misplaced", "should_have_dropped", "other"]
_ID = re.compile(r"^[0-9a-f]{64}$")


def _page(title: str, body: str) -> bytes:
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font:14px system-ui;margin:16px;max-width:1200px}}.cols{{display:grid;grid-template-columns:1fr 1fr 1fr;
gap:12px}}pre{{white-space:pre-wrap;background:#f4f4f4;padding:8px;font-size:12px}}td,th{{padding:2px 6px;
border-bottom:1px solid #ddd}}</style></head><body>{body}</body></html>""".encode()


def serve(out: Path, work: Path, batch_id: str, sample: int, seed: int, port: int) -> None:
    staged = out / "staged" / batch_id
    logs = {}
    for line in (out / "logs" / f"{batch_id}.calls.jsonl").read_text().splitlines():
        d = json.loads(line)
        logs[d["call_id"]] = d
    ids = sorted(p.stem for p in staged.glob("*.wav"))
    pick = sorted(random.Random(seed).sample(ids, min(sample, len(ids))))
    manifest = json.loads((out / "logs" / f"{batch_id}.manifest.json").read_text())
    digest = manifest_digest(manifest)
    work.mkdir(parents=True, exist_ok=True)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # no request logging: URLs carry call ids only, but stay quiet anyway
            pass

        def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            parts = u.path.strip("/").split("/")
            if u.path == "/":
                rows = "".join(f'<li><a href="/call/{i}">{i[:16]}</a> {len(logs.get(i, {}).get("removals", []))}'
                               f' removals</li>' for i in pick)
                form = "".join(f'<option value="{r}">{r}</option>' for r in REASONS)
                body = (f"<h1>Batch {html.escape(batch_id)}</h1><p>{len(pick)} of {len(ids)} staged calls, sample "
                        f"seed {seed}. Manifest digest <code>{digest[:16]}</code>. Listen to every sampled call "
                        f"before deciding. A sample does not measure recall (plan §9.3).</p><ol>{rows}</ol>"
                        f'<form method="post" action="/decide"><p>Reviewer code <input name="reviewer" '
                        f'pattern="[a-z0-9][a-z0-9_-]{{0,31}}" required> Reason <select name="reason">{form}</select>'
                        f'</p><p>Note (stays in work/, BPO only)<br><textarea name="note" cols="80"></textarea></p>'
                        f'<button name="decision" value="approve">Approve batch</button> '
                        f'<button name="decision" value="reject">Reject batch</button></form>')
                return self._send(200, _page(batch_id, body))
            if len(parts) == 2 and parts[0] == "call" and _ID.match(parts[1]) and parts[1] in pick:
                cid = parts[1]
                t = json.loads((staged / f"{cid}.json").read_text())
                tr = {ch: " ".join(w["t"] for w in ws) for ch, ws in t["channels"].items()}
                lg = json.dumps(logs.get(cid, {}), indent=1)
                body = (f'<p><a href="/">back</a></p><h2>{cid[:16]}</h2><audio controls src="/audio/{cid}">'
                        f'</audio><div class="cols"><div><h3>Agent</h3><pre>{html.escape(tr.get("agent", ""))}</pre>'
                        f'</div><div><h3>Customer</h3><pre>{html.escape(tr.get("customer", ""))}</pre></div>'
                        f'<div><h3>Log</h3><pre>{html.escape(lg)}</pre></div></div>')
                return self._send(200, _page(cid[:16], body))
            if len(parts) == 2 and parts[0] == "audio" and _ID.match(parts[1]) and parts[1] in pick:
                return self._send(200, (staged / f"{parts[1]}.wav").read_bytes(), "audio/wav")
            return self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path != "/decide":
                return self._send(404, b"not found", "text/plain")
            n = int(self.headers.get("Content-Length", "0"))
            q = {k: v[0] for k, v in parse_qs(self.rfile.read(min(n, 65536)).decode()).items()}
            reason = q.get("reason", "")
            if reason not in REASONS or q.get("decision") not in ("approve", "reject"):
                return self._send(400, b"bad request", "text/plain")
            approved = q["decision"] == "approve"
            if approved and reason != "ok":
                return self._send(400, b"approve needs reason ok", "text/plain")
            try:
                record_approval(out, batch_id, digest, q.get("reviewer", ""), approved, reason)
            except ValueError:
                return self._send(400, b"reviewer must be a short code", "text/plain")
            if q.get("note"):
                with open(work / f"{batch_id}.review-notes.jsonl", "a") as f:
                    f.write(json.dumps({"at": int(time.time()), "reviewer": q.get("reviewer"),
                                        "note": q["note"]}) + "\n")
            return self._send(200, _page("recorded", f'<p>Recorded: {q["decision"]} ({reason}). '
                                                      f'<a href="/">back</a></p>'))

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"review: http://127.0.0.1:{port}/  (batch {batch_id}, {len(pick)} calls)")
    srv.serve_forever()
