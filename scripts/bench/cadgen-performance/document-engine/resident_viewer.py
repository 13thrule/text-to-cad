#!/usr/bin/env python3
"""Bounded resident edit/viewer integration harness; not a public viewer backend.

Serves only the two accepted benchmark fixtures, a built client and exact mesh
assets from one owned dispatcher. All CAD outputs and scratch data stay in models.
This endpoint does not implement public file catalogs, source watching or naming.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import threading
import time
from urllib.parse import parse_qs, urlsplit

REPO = Path(__file__).resolve().parents[4]
SOURCE = Path(__file__).with_suffix(".js")
LIMIT = 256 * 1024**2


class Session:
    def __init__(self, scratch):
        from cadgen._document.dispatch import DocumentDispatcher
        self.scratch = scratch
        self.dispatcher = DocumentDispatcher(scratch / "store")
        self.lock = threading.Lock()
        self.revision = None
        self.assets = {}
        self.token = secrets.token_hex(24)

    def generate(self, value):
        if type(value) is not dict or set(value) != {"model", "radius", "z", "known", "render"}:
            raise ValueError("expected model, radius, z, render and known asset IDs")
        model, radius, z, known, render = (value[key] for key in ("model", "radius", "z", "known", "render"))
        if type(render) is not bool:
            raise ValueError("render must be a boolean")
        if model not in ("plate", "assembly24"):
            raise ValueError("unknown bounded fixture")
        if type(radius) not in (int, float) or not 2 <= radius <= 4:
            raise ValueError("hole radius must be within 2..4 mm")
        if type(z) not in (int, float) or not 0 <= z <= 12:
            raise ValueError("placement must be within 0..12 mm")
        if type(known) is not list or len(known) > 64 or any(type(item) is not str for item in known):
            raise ValueError("invalid known asset IDs")
        payload = (REPO / "models/performance_document" / f"{model}.py").read_text()
        payload = payload.replace("HOLE_RADIUS = 3.0  # BENCH_GEOMETRY", f"HOLE_RADIUS = {radius!r}  # BENCH_GEOMETRY")
        payload = payload.replace("PLACEMENT_Z = 0.0  # BENCH_PLACEMENT", f"PLACEMENT_Z = {z!r}  # BENCH_PLACEMENT").encode()
        path = self.scratch / "source" / f"{model}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            started = time.perf_counter()
            envelope, _ = self.dispatcher.submit("generate", path=str(path),
                digest=hashlib.sha256(payload).hexdigest(), function=None, payloads=(payload,), timeout=60).result()
            result = envelope["result"]
            generated = time.perf_counter()
            next_revision = result["revision"]
            try:
                envelope, packets = self.dispatcher.submit("display", lease=next_revision,
                    options={"edges": not render},
                    known=[item for item in known if item in self.assets], timeout=60).result()
                response = envelope["result"]
                displayed = time.perf_counter()
                manifest = json.loads(packets[0])
                next_assets = dict(self.assets)
                for entry, packet in zip(response["assets"], packets[1:], strict=True):
                    if hashlib.sha256(packet).hexdigest() != entry["identity"] or len(packet) != entry["bytes"]:
                        raise ValueError("worker asset did not match its exact receipt")
                    next_assets[entry["identity"]] = packet
                required = {row["mesh"] for row in manifest["prototypes"].values()}
                next_assets = {key: next_assets[key] for key in required}
                if sum(map(len, next_assets.values())) > LIMIT:
                    raise ValueError("resident harness asset budget exceeded")
            except BaseException:
                self.dispatcher.submit("release", lease=next_revision).result()
                raise
            previous = self.revision
            self.revision, self.assets = next_revision, next_assets
            if previous is not None:
                self.dispatcher.submit("release", lease=previous).result()
            return {"manifest": manifest, "generation": result,
                    "generationMs": (generated-started)*1000,
                    "displayMs": (displayed-generated)*1000,
                    "transferredMeshes": len(response["assets"]),
                    "transferredMeshBytes": sum(len(packet) for packet in packets[1:])}

    def query(self, value):
        if type(value) is not dict or set(value) != {"reference"}:
            raise ValueError("expected one exact topology reference")
        with self.lock:
            if self.revision is None:
                raise ValueError("generate a fixture first")
            result, _ = self.dispatcher.submit("query", lease=self.revision,
                references=[value["reference"]], space="world", timeout=30).result()
            return result["result"]

    def close(self):
        self.dispatcher.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    scratch = args.scratch.resolve()
    if not scratch.is_relative_to(REPO / "models"):
        parser.error("scratch must be inside this checkout's models directory")
    scratch.mkdir(parents=True, exist_ok=True)
    bundle = scratch / "resident-viewer.js"
    esbuild = REPO / "apps/viewer/node_modules/.bin/esbuild"
    subprocess.run([str(esbuild), str(SOURCE), "--bundle", "--format=esm", f"--outfile={bundle}"], check=True)
    session = Session(scratch)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send(self, status, payload, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            url = urlsplit(self.path)
            if parse_qs(url.query).get("token") != [session.token]:
                return self.send(403, b"{}")
            if url.path == "/":
                html = f'''<!doctype html><meta charset="utf-8"><title>Resident document review</title>
<style>body{{margin:0;background:#eee;font:13px system-ui}}header{{padding:12px;display:flex;gap:8px;align-items:center}}pre{{position:absolute;right:0;top:45px;width:310px;margin:0;box-sizing:border-box;background:#fff;padding:12px;max-height:calc(100vh - 45px);overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}}canvas{{display:block}}</style>
<header><strong>Resident document review</strong><select id="model"><option>assembly24</option><option>plate</option></select>
<select id="view"><option value="inspect-light">Inspect light</option><option value="inspect-dark">Inspect dark</option><option value="render-light">Render light</option><option value="render-dark">Render dark</option></select>
<button id="unchanged">Rebuild unchanged</button><button id="geometry">Change holes</button><button id="placement">Move one part</button><span id="status">Loading</span></header>
<pre id="facts"></pre><script type="module" src="/client.js?token={session.token}"></script>'''
                return self.send(200, html.encode(), "text/html; charset=utf-8")
            if url.path == "/client.js":
                return self.send(200, bundle.read_bytes(), "text/javascript")
            if url.path.startswith("/mesh/"):
                with session.lock:
                    payload = session.assets.get(url.path.removeprefix("/mesh/"))
                if payload is not None:
                    return self.send(200, payload, "application/octet-stream")
            self.send(404, b"{}")

        def do_POST(self):
            if self.headers.get("X-Review-Token") != session.token:
                return self.send(403, b"{}")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("bounded JSON body required")
                value = json.loads(self.rfile.read(length))
                if self.path == "/generate":
                    result = session.generate(value)
                elif self.path == "/query":
                    result = session.query(value)
                else:
                    return self.send(404, b"{}")
                self.send(200, json.dumps(result, allow_nan=False).encode())
            except Exception as error:
                self.send(400, json.dumps({"error": str(error)}).encode())

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"http://127.0.0.1:{server.server_port}/?token={session.token}", flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        server.server_close()
        session.close()


if __name__ == "__main__":
    main()
