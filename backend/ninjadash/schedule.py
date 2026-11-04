"""Built-in screen schedule (no Home Assistant needed).

Settings (in /etc/ninjadash/ninjadash.env, or: sudo ninjadash schedule set 07:00 19:00 mon-fri):
  SCREEN_ON=07:00          screen on at
  SCREEN_OFF=19:00         screen off at (may be after midnight, e.g. 02:00)
  SCREEN_DAYS=mon-fri      days the screen comes on: mon-fri, mon,wed,fri, weekdays, daily, 1-5,
                           German names work too (mo-fr)
  SCREEN_OFF_DATES=        extra days off, e.g. 2026-12-24,2026-12-25 or 2026-12-24..2027-01-01

The schedule acts at the switch times only: Home Assistant or `ninjadash screen on|off` can override
it until the next scheduled change. At startup it applies the current state right away, so a reboot
on a Saturday keeps the screen off.
"""
from __future__ import annotations

import datetime as dt

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
ALIASES = {
    "mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6,                       # German
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3, "freitag": 4, "samstag": 5, "sonntag": 6,
    "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6,
}
GROUPS = {"weekdays": {0, 1, 2, 3, 4}, "werktage": {0, 1, 2, 3, 4}, "weekend": {5, 6}, "wochenende": {5, 6},
          "daily": set(range(7)), "all": set(range(7)), "everyday": set(range(7)), "täglich": set(range(7))}


def parse_time(text: str) -> int:
    """'07:00' / '7:30' / '7' -> minutes after midnight."""
    s = str(text).strip()
    h, _, m = s.partition(":")
    if not h.isdigit() or (m and not m.isdigit()):
        raise ValueError(f"not a time: {text!r} (use HH:MM, e.g. 07:00)")
    hh, mm = int(h), int(m or 0)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"not a time: {text!r}")
    return hh * 60 + mm


def parse_days(text: str) -> set[int]:
    days: set[int] = set()
    for part in str(text or "").lower().replace(" ", "").split(","):
        if not part:
            continue
        if part in GROUPS:
            days |= GROUPS[part]
        elif "-" in part:
            a, _, b = part.partition("-")
            if a not in ALIASES or b not in ALIASES:
                raise ValueError(f"unknown days: {part!r}")
            i, j = ALIASES[a], ALIASES[b]
            days |= set(range(i, j + 1)) if i <= j else set(range(i, 7)) | set(range(0, j + 1))
        elif part in ALIASES:
            days.add(ALIASES[part])
        else:
            raise ValueError(f"unknown day: {part!r} (use e.g. mon-fri)")
    if not days:
        raise ValueError("no days given")
    return days


def parse_dates(text: str) -> set[dt.date]:
    dates: set[dt.date] = set()
    for part in str(text or "").replace(" ", "").split(","):
        if not part:
            continue
        if ".." in part:
            a, _, b = part.partition("..")
            d, end = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
            if (end - d).days > 400:
                raise ValueError(f"date range too long: {part!r}")
            while d <= end:
                dates.add(d)
                d += dt.timedelta(days=1)
        else:
            dates.add(dt.date.fromisoformat(part))
    return dates


class Schedule:
    def __init__(self, on: str, off: str, days: str = "mon-fri", off_dates: str = ""):
        self.on_text, self.off_text, self.days_text = on, off, days or "mon-fri"
        self.on, self.off = parse_time(on), parse_time(off)
        if self.on == self.off:
            raise ValueError("SCREEN_ON and SCREEN_OFF must differ")
        self.days = parse_days(self.days_text)
        self.off_dates = parse_dates(off_dates)

    @classmethod
    def from_values(cls, values: dict) -> "Schedule | None":
        on, off = (values.get("SCREEN_ON") or "").strip(), (values.get("SCREEN_OFF") or "").strip()
        if not on or not off:
            return None
        return cls(on, off, values.get("SCREEN_DAYS") or "mon-fri", values.get("SCREEN_OFF_DATES") or "")

    def _active_day(self, day: dt.date) -> bool:
        return day.weekday() in self.days and day not in self.off_dates

    def is_on(self, now: dt.datetime) -> bool:
        minute = now.hour * 60 + now.minute
        end = self.off if self.off > self.on else self.off + 1440        # an off time after midnight
        for back in (0, 1):                                              # today, and yesterday's overnight run
            day = now.date() - dt.timedelta(days=back)
            t = minute + back * 1440
            if self._active_day(day) and self.on <= t < end:
                return True
        return False

    def next_change(self, now: dt.datetime) -> tuple[dt.datetime, bool] | None:
        state = self.is_on(now)
        t = now.replace(second=0, microsecond=0)
        for _ in range(16 * 1440):                                       # look up to 16 days ahead
            t += dt.timedelta(minutes=1)
            s = self.is_on(t)
            if s != state:
                return t, s
        return None

    def describe(self, now: dt.datetime) -> dict:
        nxt = self.next_change(now)
        return {
            "enabled": True, "on": self.on_text, "off": self.off_text,
            "days": ",".join(DAYS[d] for d in sorted(self.days)),
            "offDates": sorted(d.isoformat() for d in self.off_dates if d >= now.date())[:20],
            "nowScheduled": "on" if self.is_on(now) else "off",
            "next": {"state": "on" if nxt[1] else "off", "at": nxt[0].strftime("%a %d %b %H:%M")} if nxt else None,
        }
