"""The poller: fetches from NinjaOne on a schedule and keeps the latest summary in memory."""
from __future__ import annotations

import logging
import threading
import time

from . import __version__
from .classify import Classifier
from .config import Config
from .demo import demo_summary
from .history import History
from .ninja import NinjaClient, NinjaError
from .summary import Snapshot, build_summary

log = logging.getLogger("ninjadash")
UNAVAILABLE_RETRY = 3600      # re-try endpoints that answered 403/404 once an hour


class App:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.clf = Classifier(cfg.rules)
        self.history = History(cfg.history_db)
        self.client = NinjaClient(cfg.api_base, cfg.client_id, cfg.client_secret, cfg.scope) if cfg.has_credentials else None
        self.snap = Snapshot()
        self._lock = threading.Lock()
        self._summary: dict | None = None
        self.last_success: float | None = None
        self.error: str | None = None
        self._next_slow = 0.0
        self._next_orgs = 0.0
        self._unavailable: dict[str, float] = {}
        self._stop = threading.Event()
        self.screen_on = True              # switched by Home Assistant via /api/screen
        self.screen_changed = time.time()
        self.screen_agent_seen = 0.0       # last poll from the kiosk's screen agent

    @property
    def demo(self) -> bool:
        return self.cfg.demo or not self.cfg.has_credentials

    # ---- public -----------------------------------------------------------
    def summary(self) -> dict:
        now = time.time()
        with self._lock:
            body = dict(self._summary) if self._summary else None
        if self.demo:
            body = demo_summary(now)
        meta = {
            "version": __version__,
            "generatedAt": now,
            "lastSuccess": now if self.demo else self.last_success,
            "error": self.error,
            "demo": self.demo,
            "setupNeeded": not self.cfg.has_credentials,
            "settingsFile": str(self.cfg.env_file or "/etc/ninjadash/ninjadash.env"),
            "theme": {"mode": self.cfg.theme, "lightFrom": self.cfg.light_from, "lightUntil": self.cfg.light_until},
            "ready": body is not None,
        }
        return {**(body or {}), **meta}

    def screen(self) -> dict:
        return {
            "on": self.screen_on,
            "state": "on" if self.screen_on else "off",
            "changed": self.screen_changed,
            "agent": time.time() - self.screen_agent_seen < 15,
        }

    def set_screen(self, want: str) -> dict:
        want = str(want or "").strip().lower()
        if want not in ("on", "off", "toggle", "true", "false", "1", "0"):
            raise ValueError("state must be on, off or toggle")
        new = (not self.screen_on) if want == "toggle" else want in ("on", "true", "1")
        if new != self.screen_on:
            self.screen_on = new
            self.screen_changed = time.time()
            log.info("Screen switched %s", "on" if new else "off")
        return self.screen()

    def healthy(self) -> bool:
        if self.demo:
            return True
        return self.last_success is not None and time.time() - self.last_success < 10 * 60

    def start(self) -> None:
        if self.demo:
            log.info("No API client configured (or DEMO=1): serving example data")
            return
        threading.Thread(target=self._run, name="poller", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    # ---- polling ----------------------------------------------------------
    def _optional(self, name: str, fn):
        """Call an endpoint that may not exist for this account. Returns None when unavailable."""
        now = time.time()
        if self._unavailable.get(name, 0) > now:
            return None
        try:
            result = fn()
            self._unavailable.pop(name, None)
            return result
        except NinjaError as e:
            if e.status in (400, 403, 404, 405, 501):
                if name not in self._unavailable:
                    log.info("%s not available for this account (%s); using alerts instead", name, e.status)
                self._unavailable[name] = now + UNAVAILABLE_RETRY
                return None
            raise

    def poll_once(self) -> None:
        now = time.time()
        c = self.client
        if now >= self._next_orgs or not self.snap.orgs:
            self.snap.orgs = c.organizations()
            self._next_orgs = now + 3600
        self.snap.devices = c.devices()
        self.snap.alerts = c.alerts()
        if now >= self._next_slow:
            self.snap.av_status = self._optional("antivirus-status", lambda: c.query("/v2/queries/antivirus-status"))
            self.snap.av_threats = self._optional("antivirus-threats", lambda: c.query("/v2/queries/antivirus-threats"))
            self.snap.backup_jobs = self._optional("backup-jobs", c.backup_jobs)
            self._next_slow = now + self.cfg.poll_slow
        summary = build_summary(self.snap, self.clf, self.history, time.time())
        with self._lock:
            self._summary = summary
        self.last_success = time.time()
        self.error = None

    def _run(self) -> None:
        backoff = self.cfg.poll_fast
        while not self._stop.is_set():
            try:
                self.poll_once()
                backoff = self.cfg.poll_fast
                log.info("Synced: %d devices, %d alerts", len(self.snap.devices), len(self.snap.alerts))
            except NinjaError as e:
                self.error = str(e)
                log.error("%s", e)
                backoff = min(backoff * 2, 600)
            except Exception as e:                       # never let the poller die
                self.error = f"Unexpected error: {e}"
                log.exception("Poll failed")
                backoff = min(backoff * 2, 600)
            self._stop.wait(backoff)
