"""The built-in screen schedule: times, days, holidays, overnight runs, and how it interacts with manual switching."""
import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from ninjadash.schedule import Schedule, parse_dates, parse_days, parse_time  # noqa: E402

MON = dt.date(2026, 11, 2)          # a Monday


def at(day_offset: int, hhmm: str) -> dt.datetime:
    h, m = map(int, hhmm.split(":"))
    return dt.datetime.combine(MON + dt.timedelta(days=day_offset), dt.time(h, m))


class ParseTest(unittest.TestCase):
    def test_parsing(self):
        self.assertEqual(parse_time("07:00"), 420)
        self.assertEqual(parse_time("7"), 420)
        self.assertEqual(parse_days("mon-fri"), {0, 1, 2, 3, 4})
        self.assertEqual(parse_days("Mo-Fr"), {0, 1, 2, 3, 4})               # German
        self.assertEqual(parse_days("weekdays,sat"), {0, 1, 2, 3, 4, 5})
        self.assertEqual(parse_days("fri-mon"), {4, 5, 6, 0})                 # wraps around
        self.assertEqual(len(parse_dates("2026-12-24..2026-12-26,2027-01-01")), 4)
        for bad in ("25:00", "aa", "7:61"):
            with self.assertRaises(ValueError):
                parse_time(bad)
        with self.assertRaises(ValueError):
            parse_days("funday")
        with self.assertRaises(ValueError):
            Schedule("07:00", "07:00")


class ScheduleTest(unittest.TestCase):
    def setUp(self):
        self.s = Schedule("07:00", "19:00", "mon-fri", "2026-11-04")        # Wednesday is a holiday

    def test_weekdays(self):
        self.assertFalse(self.s.is_on(at(0, "06:59")))
        self.assertTrue(self.s.is_on(at(0, "07:00")))
        self.assertTrue(self.s.is_on(at(0, "18:59")))
        self.assertFalse(self.s.is_on(at(0, "19:00")))

    def test_weekend_and_holiday_stay_off(self):
        for day in (2, 5, 6):                                                 # Wed (holiday), Sat, Sun
            for t in ("00:00", "07:00", "12:00", "18:59"):
                self.assertFalse(self.s.is_on(at(day, t)), (day, t))
        self.assertTrue(self.s.is_on(at(3, "12:00")))                         # Thursday normal again

    def test_next_change_over_the_weekend(self):
        nxt, state = self.s.next_change(at(4, "19:30"))                      # Friday evening
        self.assertEqual((nxt, state), (at(7, "07:00"), True))               # Monday 07:00
        nxt, state = self.s.next_change(at(0, "12:00"))
        self.assertEqual((nxt, state), (at(0, "19:00"), False))
        self.assertEqual(self.s.describe(at(4, "19:30"))["next"]["at"], "Mon 09 Nov 07:00")

    def test_overnight_schedule(self):
        s = Schedule("22:00", "06:00", "fri")                                # Friday night shift
        self.assertTrue(s.is_on(at(4, "23:00")))
        self.assertTrue(s.is_on(at(5, "05:59")))                             # Saturday morning, from Friday
        self.assertFalse(s.is_on(at(5, "06:00")))
        self.assertFalse(s.is_on(at(5, "23:00")))                            # Saturday is not a run day

    def test_disabled_without_times(self):
        self.assertIsNone(Schedule.from_values({"SCREEN_ON": "", "SCREEN_OFF": ""}))


class AppScheduleTest(unittest.TestCase):
    def make_app(self, env: str):
        from ninjadash.app import App
        from ninjadash.config import load_config
        tmp = tempfile.mkdtemp()
        p = Path(tmp, "x.env")
        p.write_text(env + f"\nHISTORY_DB={tmp}/h.sqlite\n")
        os.environ["NINJADASH_ENV"] = str(p)
        try:
            return App(load_config())
        finally:
            del os.environ["NINJADASH_ENV"]

    def test_switches_at_transitions_only(self):
        app = self.make_app("SCREEN_ON=07:00\nSCREEN_OFF=19:00\nSCREEN_DAYS=mon-fri")
        app.schedule_tick(at(5, "10:00"))                    # boot on a Saturday: off right away
        self.assertFalse(app.screen_on)
        app.set_screen("on")                                 # someone switches it on by hand / Home Assistant
        app.schedule_tick(at(5, "10:01"))
        self.assertTrue(app.screen_on)                       # the schedule doesn't fight that
        app.schedule_tick(at(7, "07:00"))                    # Monday 07:00: on (already on)
        app.schedule_tick(at(7, "19:00"))                    # Monday 19:00: off
        self.assertFalse(app.screen_on)
        app.schedule_tick(at(8, "07:00"))
        self.assertTrue(app.screen_on)
        info = app.screen()["schedule"]
        self.assertTrue(info["enabled"])
        self.assertEqual(info["days"], "mon,tue,wed,thu,fri")

    def test_bad_setting_is_reported_not_fatal(self):
        app = self.make_app("SCREEN_ON=7am\nSCREEN_OFF=19:00")
        self.assertIsNone(app.schedule)
        self.assertIn("Screen schedule ignored", app.screen()["schedule"]["error"])


if __name__ == "__main__":
    unittest.main()
