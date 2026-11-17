"""Run: python3 -m unittest discover -s tests   (from the repo root)."""
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tests"))

import fake_ninja  # noqa: E402
from ninjadash.classify import Classifier  # noqa: E402
from ninjadash.config import load_rules, DEFAULT_RULES  # noqa: E402
from ninjadash.history import History  # noqa: E402
from ninjadash.summary import Snapshot, build_summary  # noqa: E402


def make_summary():
    clf = Classifier(load_rules(DEFAULT_RULES))
    snap = Snapshot(orgs=fake_ninja.ORGS, devices=fake_ninja.DEVICES, alerts=fake_ninja.ALERTS,
                    av_status=fake_ninja.AV_STATUS, av_threats=fake_ninja.AV_THREATS, backup_jobs=None)
    tmp = tempfile.mkdtemp()
    return build_summary(snap, clf, History(f"{tmp}/h.sqlite"), time.time())


class ClassifierTest(unittest.TestCase):
    def setUp(self):
        self.clf = Classifier(load_rules(DEFAULT_RULES))

    def test_tiers(self):
        self.assertEqual(self.clf.tier("WINDOWS_SERVER", "x"), "server")
        self.assertEqual(self.clf.tier("HYPERV_VMM_HOST", "x"), "server")
        self.assertEqual(self.clf.tier("NMS_NAS", "x"), "server")
        self.assertEqual(self.clf.tier("WINDOWS_WORKSTATION", "x"), "workstation")
        self.assertEqual(self.clf.tier("MAC", "x"), "workstation")
        self.assertIsNone(self.clf.tier("VMWARE_VM_GUEST", "x"))

    def test_long_offline_devices_are_hidden(self):
        import copy
        now = time.time()
        devs = copy.deepcopy(fake_ninja.DEVICES)
        target = next(d for d in devs if d["id"] == 1)                 # SRV-FS01: has alerts and a full volume
        target.update(offline=True, lastContact=now - 40 * 86400)
        snap = Snapshot(orgs=fake_ninja.ORGS, devices=devs, alerts=fake_ninja.ALERTS, volumes=fake_ninja.VOLUMES)
        clf = Classifier(load_rules(DEFAULT_RULES))
        s = build_summary(snap, clf, None, now)
        names = [a["name"] for a in s["affected"]]
        self.assertNotIn("SRV-FS01", names)
        self.assertNotIn("SRV-FS01", [h["name"] for h in s["healthy"]])
        self.assertNotIn("SRV-FS01", [i["device"] for i in s["updates"]["storage"]["items"]])
        self.assertEqual(s["hiddenOffline"]["servers"], 1)
        target["lastContact"] = now - 10 * 86400                          # offline 10 days: still shown
        s = build_summary(snap, clf, None, now)
        self.assertIn("SRV-FS01", [a["name"] for a in s["affected"]])
        self.assertEqual(s["hiddenOffline"]["servers"], 0)

    def test_hide_offline_days_comes_from_the_settings_file(self):
        import copy
        import os
        from unittest import mock
        from ninjadash.config import load_config
        now = time.time()
        devs = copy.deepcopy(fake_ninja.DEVICES)
        next(d for d in devs if d["id"] == 1).update(offline=True, lastContact=now - 40 * 86400)
        snap = Snapshot(orgs=fake_ninja.ORGS, devices=devs, alerts=fake_ninja.ALERTS)
        tmp = Path(tempfile.mkdtemp())
        for value, hidden in (("60", 0), ("0", 0), ("", 1), ("20", 1)):
            (tmp / "ninjadash.env").write_text(f"NINJA_CLIENT_ID=\nHIDE_OFFLINE_DAYS={value}   # comment\n")
            env = {"NINJADASH_ENV": str(tmp / "ninjadash.env"), "NINJADASH_RULES": str(DEFAULT_RULES)}
            with mock.patch.dict(os.environ, env):
                os.environ.pop("HIDE_OFFLINE_DAYS", None)
                cfg = load_config()
            s = build_summary(snap, Classifier(cfg.rules), None, now)
            self.assertEqual(s["hiddenOffline"]["servers"], hidden, f"HIDE_OFFLINE_DAYS={value!r}")

    def test_custom_field_condition_text(self):
        from ninjadash.summary import alert_label
        cases = {
            "Benutzerdefinierte Felder Bedingung wurde erfüllt: Vaeem Backup Fehler": "Vaeem Backup Fehler",
            "Benutzerdefinierte Felder Bedingung wurde erfüllt - Vaeem Backup Fehler": "Vaeem Backup Fehler",
            "Benutzerdefinierte Felder Bedingung wurde erfüllt (Vaeem Backup Fehler)": "Vaeem Backup Fehler",
            "Benutzerdefiniertes Feld Bedingung wurde erfüllt für Vaeem Backup Fehler": "Vaeem Backup Fehler",
            "Custom Fields condition was met: Veeam backup failed": "Veeam backup failed",
            "Custom field condition triggered - Veeam backup failed": "Veeam backup failed",
            "RAID 5 degraded · disk 2 failed": "RAID 5 degraded · disk 2 failed",          # other alerts untouched
            "Customer portal certificate expires": "Customer portal certificate expires",
        }
        for text, want in cases.items():
            self.assertEqual(alert_label({}, "", text), want, text)
        # only the generic phrase: use the condition's own name
        self.assertEqual(alert_label({"sourceName": "Vaeem Backup Fehler"}, "", "Benutzerdefinierte Felder Bedingung wurde erfüllt"),
                         "Vaeem Backup Fehler")
        # generic subject, the detail is in the message
        self.assertEqual(alert_label({}, "Custom Fields condition was met", "Veeam backup failed\nmore text"), "Veeam backup failed")

    def test_warning_or_error_from_the_status_text(self):
        from ninjadash.summary import text_level
        self.assertEqual(text_level("Vaeem Backup Fehler"), "critical")
        self.assertEqual(text_level("Backup Status: Warnung"), "warning")
        self.assertEqual(text_level("RAID Status = Warning"), "warning")
        self.assertEqual(text_level("Raidwarnung"), "warning")
        self.assertEqual(text_level("Backup Status von Fehler zu Warnung"), "warning")
        self.assertEqual(text_level("Backup Status von Kein Fehler zu Fehler"), "critical")
        self.assertEqual(text_level("RAID Status von kein Fehler zu Warnung"), "warning")
        self.assertEqual(text_level("RAID 5 degraded"), None)
        self.assertEqual(text_level("Veeam backup failed"), "critical")

    def test_backup_warning_is_yellow_and_after_errors(self):
        import copy
        now = time.time()
        alerts = [{"uid": "w1", "deviceId": 1, "severity": "MAJOR", "createTime": now - 60,
                   "subject": "", "message": "Benutzerdefinierte Felder Bedingung wurde erfüllt: Backup Status Warnung"},
                  {"uid": "e1", "deviceId": 2, "severity": "MAJOR", "createTime": now - 3600,
                   "subject": "", "message": "Benutzerdefinierte Felder Bedingung wurde erfüllt: Backup Status Fehler"},
                  {"uid": "r1", "deviceId": 3, "severity": "MAJOR", "createTime": now - 30,
                   "subject": "", "message": "Benutzerdefinierte Felder Bedingung wurde erfüllt: RAID Status Warnung"}]
        devs = copy.deepcopy(fake_ninja.DEVICES)
        for d in devs:
            d["offline"] = False
        snap = Snapshot(orgs=fake_ninja.ORGS, devices=devs, alerts=alerts)
        s = build_summary(snap, Classifier(load_rules(DEFAULT_RULES)), None, now)
        by_text = {i["text"]: i for srv in s["affected"] for i in srv["issues"]}
        self.assertEqual(by_text["Backup Status Warnung"]["severity"], "warning")
        self.assertEqual(by_text["Backup Status Fehler"]["severity"], "critical")
        self.assertEqual(by_text["RAID Status Warnung"]["severity"], "warning")
        self.assertEqual(by_text["RAID Status Warnung"]["category"], "hardware")
        self.assertEqual(s["affected"][0]["state"], "critical")           # errors first, even when older
        self.assertEqual(s["pillars"]["hardware"]["state"], "warning")
        self.assertEqual(s["pillars"]["backup"]["state"], "critical")

    def test_ninjaone_warning_stays_yellow_even_with_fehler_in_the_name(self):
        import copy
        now = time.time()
        msg = "Benutzerdefinierte Felder Bedingung wurde erfüllt: Vaeem Backup Fehler"
        alerts = [{"uid": "m1", "deviceId": 1, "severity": "MODERATE", "createTime": now - 60, "subject": "", "message": msg},
                  {"uid": "m2", "deviceId": 2, "severity": "MINOR", "createTime": now - 60, "subject": "", "message": msg},
                  {"uid": "c1", "deviceId": 3, "severity": "CRITICAL", "createTime": now - 60, "subject": "", "message": msg}]
        devs = copy.deepcopy(fake_ninja.DEVICES)
        for d in devs:
            d["offline"] = False
        s = build_summary(Snapshot(orgs=fake_ninja.ORGS, devices=devs, alerts=alerts),
                          Classifier(load_rules(DEFAULT_RULES)), None, now)
        states = {srv["name"]: srv["state"] for srv in s["affected"]}
        self.assertEqual(states["SRV-FS01"], "warning")       # NinjaOne MODERATE: text "Fehler" must not make it red
        self.assertEqual(states["SRV-VEEAM"], "warning")      # MINOR shows as a warning too
        self.assertEqual(states["SRV-SQL01"], "critical")     # NinjaOne CRITICAL + "Fehler": red

    def test_level_from_the_custom_field_when_the_alert_text_has_none(self):
        import copy
        from ninjadash.summary import needs_fields, field_level
        clf = Classifier(load_rules(DEFAULT_RULES))
        now = time.time()
        msg = "Benutzerdefinierte Felder Bedingung wurde erfüllt: 'Veeam Backup & Replication prüfen'"
        alerts = [{"uid": f"v{d}", "deviceId": d, "severity": "MAJOR", "priority": "MEDIUM", "createTime": now - 60,
                   "subject": "", "message": msg} for d in (1, 2, 3)]
        self.assertTrue(needs_fields(alerts[0], clf))
        self.assertFalse(needs_fields({"severity": "MAJOR", "message": "Server RAID Status - Warnung"}, clf))
        fields = {1: {"veeamStatus": "Warnung", "raidStatus": "Fehler", "notes": "x"},     # the Veeam field wins over RAID
                  2: {"veeamStatus": "Fehler", "raidStatus": "Kein Fehler"},
                  3: {"raidStatus": "Kein Fehler", "owner": "IT"}}                         # no status field: stays red
        devs = copy.deepcopy(fake_ninja.DEVICES)
        for d in devs:
            d["offline"] = False
        s = build_summary(Snapshot(orgs=fake_ninja.ORGS, devices=devs, alerts=alerts, custom_fields=fields), clf, None, now)
        states = {srv["name"]: srv["state"] for srv in s["affected"]}
        self.assertEqual(states["SRV-FS01"], "warning")
        self.assertEqual(states["SRV-VEEAM"], "critical")
        self.assertEqual(states["SRV-SQL01"], "critical")
        self.assertEqual(s["affected"][-1]["name"], "SRV-FS01")             # warnings after errors
        self.assertEqual(field_level({"Veeam_Status": {"text": "Warnung"}}, "Veeam Backup"), ("warning", "Veeam_Status = Warnung"))
        self.assertEqual(field_level({"status": "Warnung"}, "Veeam Backup")[0], "warning")   # only one status field: use it

    def test_categories(self):
        cat = lambda text, cond="": self.clf.category([cond] if cond else [], text)[0]
        self.assertEqual(cat("Veeam job 'Daily' finished with Failed"), "backup")
        self.assertEqual(cat("Synology: Drive 3 in Volume 1 has failed"), "other")      # no keyword → needs a condition match
        self.assertEqual(cat("x", "NAS drive status (SNMP)"), "hardware")
        self.assertEqual(cat("RAID 5 degraded"), "hardware")
        self.assertEqual(cat("S.M.A.R.T. predicted failure"), "hardware")
        self.assertEqual(cat("Trojan found"), "antivirus")
        self.assertEqual(cat("Disk C: is 91 % full"), "other")
        self.assertEqual(cat("CPU utilisation above 95 %"), "other")
        self.assertEqual(cat("Smartphone sync failed"), "other")                        # 'smart' alone is not a keyword


class SummaryTest(unittest.TestCase):
    def setUp(self):
        self.s = make_summary()
        self.by_name = {(a["org"], a["name"]): a for a in self.s["affected"]}

    def test_servers(self):
        names = {n for _, n in self.by_name}
        self.assertTrue({"SRV-FS01", "SRV-VEEAM", "SRV-SQL01", "HV-HOST02", "SRV-RDS02", "SRV-PRINT", "NAS-01"} <= names)
        self.assertIn(("Acme Logistics", "SRV-DC01"), self.by_name)          # critical "other" alert shows on a server
        self.assertNotIn(("Riverside Clinic", "SRV-DC01"), self.by_name)     # warning "other" alert stays hidden
        self.assertNotIn(("Riverside Clinic", "SRV-APP01"), self.by_name)    # offline for only 5 min
        self.assertEqual(self.by_name[("Internal IT", "SRV-PRINT")]["state"], "offline")
        self.assertEqual(self.by_name[("Riverside Clinic", "SRV-RDS02")]["state"], "critical")
        self.assertEqual(self.s["affected"][0]["state"], "critical")         # worst first

    def test_pillars(self):
        p = self.s["pillars"]
        self.assertEqual((p["hardware"]["servers"], p["hardware"]["workstations"]), (4, 2))   # FS01, SQL01, HV-HOST02, NAS-01 | WS-114, MBP
        self.assertEqual((p["backup"]["servers"], p["backup"]["workstations"]), (1, 0))
        self.assertEqual((p["antivirus"]["servers"], p["antivirus"]["workstations"]), (1, 2))  # RDS02 | LT-SALES-07 off, WS-RECEPTION quarantined
        self.assertEqual(p["backup"]["note"], "from NinjaOne alerts")
        self.assertEqual(p["antivirus"]["note"], "1 active · 1 quarantined")

    def test_workstations_and_counts(self):
        texts = {w["device"]: w["text"] for w in self.s["workstations"]}
        self.assertIn("LT-SALES-07", texts)
        self.assertNotIn("MBP-ANNA", [w["device"] for w in self.s["workstations"] if w["category"] == "antivirus"])
        self.assertEqual(self.s["online"]["servers"], [9, 11])
        self.assertEqual(self.s["online"]["workstations"][1], 45)
        self.assertEqual(self.s["ignoredDevices"], 1)
        self.assertEqual(sum(self.s["trend"]["hardware"]), 6)


if __name__ == "__main__":
    unittest.main()
