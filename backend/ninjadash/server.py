"""HTTP server: the dashboard page, /api/summary, /api/screen and /healthz. Stdlib only.

Access rules
- This PC (127.0.0.1 / ::1): everything. The kiosk browser and the screen agent use this.
- Other PCs, depending on REMOTE_ACCESS:
    none   -> nothing
    screen -> only /api/screen (default; for Home Assistant)
    all    -> also the dashboard itself (read-only)
- Changing the screen from another PC always needs `Authorization: Bearer <SCREEN_TOKEN>`
  (or ?token=...). Reading the screen state from another PC needs it too.
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import mimetypes
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("ninjadash.http")
SCREEN_PATHS = ("/api/screen", "/api/screen/on", "/api/screen/off", "/api/screen/toggle")


def is_local(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        if addr.version == 6 and addr.ipv4_mapped:
            addr = addr.ipv4_mapped
        return addr.is_loopback
    except ValueError:
        return False


def token_ok(expected: str, auth_header: str | None, query_token: str | None) -> bool:
    if not expected:
        return False
    given = ""
    if auth_header and auth_header.lower().startswith("bearer "):
        given = auth_header[7:].strip()
    elif query_token:
        given = query_token
    return bool(given) and hmac.compare_digest(given.encode(), expected.encode())


def check_access(path: str, method: str, local: bool, remote_access: str, expected_token: str,
                 auth_header: str | None, query_token: str | None) -> tuple[int, str]:
    """Returns (status, message); 200 means allowed."""
    screen = path in SCREEN_PATHS
    if local:
        return 200, ""
    if remote_access == "none":
        return 403, "Access from other computers is switched off (REMOTE_ACCESS=none)."
    if not screen and remote_access != "all":
        return 403, "Only /api/screen is available from other computers (REMOTE_ACCESS=screen)."
    if screen:
        if not expected_token:
            return 403, "Screen control is not set up: SCREEN_TOKEN is empty."
        if not token_ok(expected_token, auth_header, query_token):
            return 401, "Missing or wrong token."
    return 200, ""


def make_handler(app, frontend: Path):
    root = frontend.resolve()
    cfg = app.cfg

    class Handler(BaseHTTPRequestHandler):
        server_version = "NinjaDash"

        def log_message(self, fmt, *args):            # quiet: the kiosk polls all the time
            log.debug("%s - %s", self.address_string(), fmt % args)

        def _send(self, status: int, body: bytes, ctype: str, cache: str = "no-store", extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, data, extra: dict | None = None):
            self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8", extra=extra)

        def _gate(self, path: str, query: dict) -> bool:
            status, msg = check_access(path, self.command, is_local(self.client_address[0]), cfg.remote_access,
                                       cfg.screen_token, self.headers.get("Authorization"), (query.get("token") or [None])[0])
            if status == 200:
                return True
            extra = {"WWW-Authenticate": 'Bearer realm="ninjadash"'} if status == 401 else None
            self._json(status, {"error": msg}, extra)
            return False

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            u = urlparse(self.path)
            path, query = u.path, parse_qs(u.query)
            if not self._gate(path, query):
                return
            if path == "/api/summary":
                return self._json(200, {**app.summary(), "screen": app.screen()})
            if path == "/api/screen":
                if "agent" in query and is_local(self.client_address[0]):
                    app.screen_agent_seen = time.time()
                return self._json(200, app.screen())
            if path in SCREEN_PATHS:
                return self._json(405, {"error": "Use POST to switch the screen."})
            if path == "/healthz":
                ok = app.healthy()
                return self._json(200 if ok else 503, {"ok": ok, "lastSuccess": app.last_success, "error": app.error, "demo": app.demo})
            return self._static(path)

        def do_POST(self):
            u = urlparse(self.path)
            path, query = u.path, parse_qs(u.query)
            if not self._gate(path, query):
                return
            if path not in SCREEN_PATHS:
                return self._json(404, {"error": "Not found"})
            want = path.rsplit("/", 1)[-1] if path != "/api/screen" else None
            if want is None:
                length = min(int(self.headers.get("Content-Length") or 0), 4096)
                raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
                try:
                    body = json.loads(raw) if raw.strip().startswith("{") else {}
                except json.JSONDecodeError:
                    body = {}
                if not body and raw:
                    body = {k: v[0] for k, v in parse_qs(raw).items()}
                want = body.get("state", (query.get("state") or [""])[0])
                if isinstance(want, bool):
                    want = "on" if want else "off"
            try:
                return self._json(200, app.set_screen(str(want)))
            except ValueError as e:
                return self._json(400, {"error": str(e)})

        def _static(self, path: str):
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
                initial = json.dumps({**app.summary(), "screen": app.screen()}, ensure_ascii=False).replace("</", "<\\/")
                body = body.replace(b'<script src="app.js"></script>',
                                    f'<script>window.NINJADASH_INITIAL={initial};</script>\n<script src="app.js"></script>'.encode())
                return self._send(200, body, ctype, "no-store")
            return self._send(200, body, ctype, "no-cache")

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True


def serve(app, host: str, port: int, frontend: Path) -> None:
    httpd = Server((host, port), make_handler(app, frontend))
    where = "this PC only" if is_local(host) else f"the network (other PCs: {app.cfg.remote_access})"
    log.info("Dashboard on http://%s:%d/ (reachable from %s)", host, port, where)
    if not is_local(host) and app.cfg.remote_access != "none" and not app.cfg.screen_token:
        log.warning("SCREEN_TOKEN is empty, so Home Assistant cannot switch the screen")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
