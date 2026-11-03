"""HTTP server: the dashboard page, /api/summary and /healthz. Stdlib only."""
from __future__ import annotations

import json
import logging
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger("ninjadash.http")


def make_handler(app, frontend: Path):
    root = frontend.resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "NinjaDash"

        def log_message(self, fmt, *args):            # quiet: the kiosk polls every 30 s
            log.debug("%s - %s", self.address_string(), fmt % args)

        def _send(self, status: int, body: bytes, ctype: str, cache: str = "no-store"):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, data):
            self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            path = self.path.split("?", 1)[0].split("#", 1)[0]
            if path == "/api/summary":
                return self._json(200, app.summary())
            if path == "/healthz":
                ok = app.healthy()
                return self._json(200 if ok else 503, {"ok": ok, "lastSuccess": app.last_success, "error": app.error, "demo": app.demo})
            if path in ("", "/"):
                path = "/index.html"
            target = (root / path.lstrip("/")).resolve()
            if root not in target.parents or not target.is_file():
                return self._send(404, b"Not found", "text/plain; charset=utf-8")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
                ctype += "; charset=utf-8"
            body = target.read_bytes()
            if target.name == "index.html":
                # Embed the current data so the first frame is already the dashboard.
                initial = json.dumps(app.summary(), ensure_ascii=False).replace("</", "<\\/")
                body = body.replace(b'<script src="app.js"></script>',
                                    f'<script>window.NINJADASH_INITIAL={initial};</script>\n<script src="app.js"></script>'.encode())
                return self._send(200, body, ctype, "no-store")
            return self._send(200, body, ctype, "no-cache")

    return Handler


def serve(app, host: str, port: int, frontend: Path) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(app, frontend))
    httpd.daemon_threads = True
    log.info("Dashboard on http://%s:%d/", host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
