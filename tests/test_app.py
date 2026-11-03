import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from ninjadash.classify import Classifier  # noqa: E402
from ninjadash.config import DEFAULT_RULES, load_config, load_rules  # noqa: E402


class AppTest(unittest.TestCase):
    def test_demo_without_credentials(self):
        tmp = tempfile.mkdtemp()
        env = Path(tmp, "x.env")
        env.write_text(f"NINJA_HOST=eu.ninjarmm.com\nNINJA_CLIENT_ID=\nNINJA_CLIENT_SECRET=\nHISTORY_DB={tmp}/h.sqlite\n")
        os.environ["NINJADASH_ENV"] = str(env)
        try:
            from ninjadash.app import App
            app = App(load_config())
            s = app.summary()
        finally:
            del os.environ["NINJADASH_ENV"]
        self.assertTrue(s["demo"])
        self.assertTrue(s["setupNeeded"])
        self.assertTrue(s["ready"])
        self.assertEqual(len(s["affected"]), 6)
        self.assertTrue(app.healthy())

    def test_local_rules_template_and_override(self):
        rules = load_rules(ROOT / "deploy/classify.local.toml")       # all examples commented out
        self.assertEqual(len(rules["rule"]), len(load_rules(DEFAULT_RULES)["rule"]))
        tmp = Path(tempfile.mkdtemp(), "r.toml")
        tmp.write_text('[[rule]]\nname="mine"\ncondition=["VBR job*"]\ncategory="backup"\n[tiers]\nserver_names=["NAS-*"]\n')
        clf = Classifier(load_rules(tmp))
        self.assertEqual(clf.category(["VBR job result"], "anything")[0], "backup")
        self.assertEqual(clf.tier("WINDOWS_WORKSTATION", "NAS-02"), "server")
        self.assertEqual(clf.category([], "RAID degraded")[0], "hardware")   # defaults still apply


if __name__ == "__main__":
    unittest.main()
