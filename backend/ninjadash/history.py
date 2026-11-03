"""Tiny SQLite store: remembers when each incident was first seen, for the 14-day trend."""
from __future__ import annotations

import datetime as dt
import sqlite3
import threading
from pathlib import Path

CATEGORIES = ("hardware", "backup", "antivirus")


class History:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, category TEXT NOT NULL, day TEXT NOT NULL)")
        self._db.commit()

    def record(self, items: list[tuple[str, str]], today: dt.date | None = None) -> None:
        """items: (stable incident key, category). Only the first sighting counts."""
        day = (today or dt.date.today()).isoformat()
        rows = [(k, c, day) for k, c in items if c in CATEGORIES]
        if not rows:
            return
        with self._lock:
            self._db.executemany("INSERT OR IGNORE INTO seen (key, category, day) VALUES (?, ?, ?)", rows)
            cutoff = ((today or dt.date.today()) - dt.timedelta(days=60)).isoformat()
            self._db.execute("DELETE FROM seen WHERE day < ?", (cutoff,))
            self._db.commit()

    def trend(self, days: int = 14, today: dt.date | None = None) -> dict[str, list[int]]:
        today = today or dt.date.today()
        first = today - dt.timedelta(days=days - 1)
        out = {c: [0] * days for c in CATEGORIES}
        with self._lock:
            rows = self._db.execute(
                "SELECT category, day, COUNT(*) FROM seen WHERE day >= ? GROUP BY category, day", (first.isoformat(),)
            ).fetchall()
        for cat, day, n in rows:
            idx = (dt.date.fromisoformat(day) - first).days
            if cat in out and 0 <= idx < days:
                out[cat][idx] = n
        return out
