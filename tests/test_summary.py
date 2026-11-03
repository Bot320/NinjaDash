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
