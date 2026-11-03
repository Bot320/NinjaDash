"""Minimal NinjaOne public API (v2) client: OAuth2 client credentials, retries, paging. Stdlib only.

READ-ONLY BY DESIGN. NinjaDash never changes anything in NinjaOne:
- The login always asks for the "monitoring" scope only (read access). It can't be configured.
- The only request that isn't a GET is the login itself (POST /ws/oauth/token).
- `get()` is the only way to call the API, and it refuses anything outside /v2/.
tests/test_readonly.py runs a full sync against a fake API and fails if any other request is sent.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("ninjadash.api")
USER_AGENT = "NinjaDash/0.3 (+wall dashboard; read-only)"
READ_ONLY_SCOPE = "monitoring"


class NinjaError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class NinjaClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str, scope: str = READ_ONLY_SCOPE, timeout: int = 30):
        self.base = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        if scope != READ_ONLY_SCOPE:
            log.warning("Ignoring scope %r: NinjaDash only ever asks for the read-only %r scope", scope, READ_ONLY_SCOPE)
        self.scope = READ_ONLY_SCOPE
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires = 0.0

    # ---- auth -------------------------------------------------------------
    def _fetch_token(self) -> None:
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
        }).encode()
        req = urllib.request.Request(
            self.base + "/ws/oauth/token", data=body, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            detail = _read_error(e)
            raise NinjaError(f"Login to NinjaOne failed ({e.code}): {detail}. Check NINJA_CLIENT_ID, NINJA_CLIENT_SECRET and NINJA_HOST.", e.code) from None
        except urllib.error.URLError as e:
            raise NinjaError(f"Cannot reach {self.base}: {e.reason}") from None
        token = data.get("access_token")
        if not token:
            raise NinjaError("NinjaOne login returned no access token")
        self._token = token
        self._token_expires = time.time() + float(data.get("expires_in", 3600))

    def _auth_header(self) -> str:
        if not self._token or time.time() > self._token_expires - 60:
            self._fetch_token()
        return f"Bearer {self._token}"

    # ---- requests ---------------------------------------------------------
    def get(self, path: str, params: dict | None = None):
        """The only way NinjaDash talks to the API: plain GET requests below /v2/ (read-only)."""
        if not path.startswith("/v2/") or ".." in path:
            raise ValueError(f"Refusing to call {path!r}: NinjaDash only reads from /v2/")
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        refreshed = False
        for attempt in range(4):
            req = urllib.request.Request(url, headers={
                "Authorization": self._auth_header(), "Accept": "application/json", "User-Agent": USER_AGENT,
            })
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                if e.code == 401 and not refreshed:
                    self._token = None
                    refreshed = True
                    continue
                if e.code == 429 or e.code >= 500:
                    wait = _retry_after(e) or min(2 ** attempt * 2, 30)
                    log.warning("GET %s -> %s, retrying in %ss", path, e.code, wait)
                    time.sleep(wait)
                    continue
                raise NinjaError(f"GET {path} failed ({e.code}): {_read_error(e)}", e.code) from None
            except urllib.error.URLError as e:
                if attempt < 3:
                    time.sleep(min(2 ** attempt * 2, 30))
                    continue
                raise NinjaError(f"Cannot reach {self.base}: {e.reason}") from None
        raise NinjaError(f"GET {path} kept failing after retries")

    def devices(self, page_size: int = 500, max_pages: int = 50) -> list[dict]:
        out: list[dict] = []
        after = None
        for _ in range(max_pages):
            batch = self.get("/v2/devices-detailed", {"pageSize": page_size, "after": after}) or []
            if not isinstance(batch, list):
                batch = batch.get("results", []) if isinstance(batch, dict) else []
            out.extend(batch)
            if len(batch) < page_size:
                break
            after = max(d.get("id", 0) for d in batch)
        return out

    def query(self, path: str, page_size: int = 1000, max_pages: int = 20) -> list[dict]:
        """`/v2/queries/*` endpoints return {"results": [...], "cursor": {"name": ...}}."""
        out: list[dict] = []
        cursor = None
        for _ in range(max_pages):
            data = self.get(path, {"pageSize": page_size, "cursor": cursor}) or {}
            if isinstance(data, list):
                out.extend(data)
                break
            results = data.get("results") or []
            out.extend(results)
            cur = data.get("cursor") or {}
            cursor = cur.get("name") if isinstance(cur, dict) else None
            if not cursor or len(results) < page_size:
                break
        return out

    def organizations(self) -> list[dict]:
        data = self.get("/v2/organizations", {"pageSize": 1000}) or []
        return data if isinstance(data, list) else data.get("results", [])

    def alerts(self) -> list[dict]:
        data = self.get("/v2/alerts") or []
        return data if isinstance(data, list) else data.get("results", [])

    def backup_jobs(self) -> list[dict]:
        data = self.get("/v2/backup/jobs") or []
        if isinstance(data, dict):
            return data.get("results") or data.get("jobs") or []
        return data


def _read_error(e: urllib.error.HTTPError) -> str:
    try:
        body = e.read().decode("utf-8", "replace")[:300]
    except Exception:
        body = ""
    finally:
        e.close()
    try:
        j = json.loads(body)
        return j.get("error_description") or j.get("error") or j.get("message") or body
    except Exception:
        return body or e.reason


def _retry_after(e: urllib.error.HTTPError) -> int | None:
    try:
        return int(e.headers.get("Retry-After", ""))
    except (TypeError, ValueError):
        return None
