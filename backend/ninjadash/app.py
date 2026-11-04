"""The poller: fetches from NinjaOne on a schedule and keeps the latest summary in memory."""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
from pathlib import Path

from . import __version__
from .classify import Classifier
from .config import Config
from .demo import demo_summary
from .history import History
from .ninja import NinjaClient, NinjaError
from .schedule import Schedule
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
        self.schedule_error: str | None = None
        try:
            self.schedule = Schedule.from_values(cfg.schedule_values)
        except ValueError as e:
            self.schedule, self.schedule_error = None, f"Screen schedule ignored: {e}"
            log.error("%s", self.schedule_error)
        self._schedule_last: bool | None = None
        self.state_file = Path(cfg.history_db).parent / "state.json"
        self.theme_mode = self._load_state().get("theme") or cfg.theme   # light | dark | auto

    # ---- small persistent state (theme chosen by Home Assistant survives a reboot) ----
    def _load_state(self) -> dict:
        try:
            data = json.loads(self.state_file.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps({"theme": self.theme_mode}))
            tmp.replace(self.state_file)
        except OSError as e:
            log.warning("Could not save %s: %s", self.state_file, e)

    def theme(self) -> dict:
        mode = self.theme_mode if self.theme_mode in ("light", "dark") else "auto"
        if mode == "auto":
            def mins(s):
                h, _, m = str(s).partition(":")
                return int(h or 0) * 60 + int(m or 0)
            now = dt.datetime.now()
            cur, a, b = now.hour * 60 + now.minute, mins(self.cfg.light_from), mins(self.cfg.light_until)
            light = (a <= cur < b) if a <= b else (cur >= a or cur < b)
            effective = "light" if light else "dark"
        else:
            effective = mode
        return {"mode": mode, "effective": effective, "dark": effective == "dark",
                "lightFrom": self.cfg.light_from, "lightUntil": self.cfg.light_until}

    def set_theme(self, want: str) -> dict:
        want = str(want or "").strip().lower()
        if want == "toggle":
            want = "light" if self.theme()["effective"] == "dark" else "dark"
        if want in ("on", "true", "1"):          # a Home Assistant switch "dark mode" on/off
            want = "dark"
        elif want in ("off", "false", "0"):
            want = "light"
        if want not in ("light", "dark", "auto"):
            raise ValueError("mode must be light, dark, auto or toggle")
        if want != self.theme_mode:
            self.theme_mode = want
            self._save_state()
            log.info("Theme set to %s", want)
        return self.theme()

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
            "theme": self.theme(),
            "ready": body is not None,
        }
        return {**(body or {}), **meta}

    def screen(self) -> dict:
        return {
            "on": self.screen_on,
            "state": "on" if self.screen_on else "off",
            "changed": self.screen_changed,
            "agent": time.time() - self.screen_agent_seen < 15,
            "theme": self.theme()["effective"],
            "schedule": self._schedule_info(),
        }

    def _schedule_info(self) -> dict:
        if not self.schedule:
            return {"enabled": False, "error": self.schedule_error}
        minute = int(time.time() // 60)                 # the kiosk asks every 2-3 s; compute once a minute
        cached = getattr(self, "_schedule_cache", None)
        if not cached or cached[0] != minute:
            self._schedule_cache = cached = (minute, self.schedule.describe(dt.datetime.now()))
        return cached[1]

    def schedule_tick(self, now: dt.datetime | None = None) -> None:
        """Switch the screen when the schedule's state changes (and once at startup)."""
        if not self.schedule:
            return
        state = self.schedule.is_on(now or dt.datetime.now())
        if state != self._schedule_last:
            self._schedule_last = state
            self.set_screen("on" if state else "off", source="schedule")

    def _run_schedule(self) -> None:
        while not self._stop.is_set():
            try:
                self.schedule_tick()
            except Exception:
                log.exception("Screen schedule failed")
            self._stop.wait(15)

    def set_screen(self, want: str, source: str = "manual") -> dict:
        want = str(want or "").strip().lower()
        if want not in ("on", "off", "toggle", "true", "false", "1", "0"):
            raise ValueError("state must be on, off or toggle")
        new = (not self.screen_on) if want == "toggle" else want in ("on", "true", "1")
        if new != self.screen_on:
            self.screen_on = new
            self.screen_changed = time.time()
            log.info("Screen switched %s (%s)", "on" if new else "off", source)
        return self.screen()

    def healthy(self) -> bool:
        if self.demo:
            return True
        return self.last_success is not None and time.time() - self.last_success < 10 * 60

    def start(self) -> None:
        if self.schedule:
            d = self.schedule.describe(dt.datetime.now())
            log.info("Screen schedule: on %s, off %s, days %s", d["on"], d["off"], d["days"])
            threading.Thread(target=self._run_schedule, name="schedule", daemon=True).start()
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
            self.snap.os_patches = self._optional("os-patches", lambda: c.query("/v2/queries/os-patches"))
            self.snap.sw_patches = self._optional("software-patches", lambda: c.query("/v2/queries/software-patches"))
            self.snap.volumes = self._optional("volumes", lambda: c.query("/v2/queries/volumes"))
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
