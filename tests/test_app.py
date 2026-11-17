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


class RedirectTest(unittest.TestCase):
    def test_target(self):
        from ninjadash.server import redirect_target
        self.assertEqual(redirect_target("ninjadash.local", "x", 8080, "/"), "http://ninjadash.local:8080/")
        self.assertEqual(redirect_target("ninjadash.local:80", "x", 8080, "/api/summary?a=1"),
                         "http://ninjadash.local:8080/api/summary?a=1")
        self.assertEqual(redirect_target("192.168.1.20", "x", 8080, "/"), "http://192.168.1.20:8080/")
        self.assertEqual(redirect_target("[fe80::1]:80", "x", 8080, "/"), "http://[fe80::1]:8080/")
        self.assertEqual(redirect_target(None, "localhost", 8080, "/"), "http://localhost:8080/")
        self.assertEqual(redirect_target("ninjadash.local", "x", 8080, "//evil.example/"), "http://ninjadash.local:8080/")
        self.assertIsNone(redirect_target("evil.example/x?", "x", 8080, "/"))
        self.assertIsNone(redirect_target("a b", "x", 8080, "/"))

    def test_port_80_forwards_to_the_dashboard(self):
        import http.client
        import socket
        from ninjadash.server import start_redirect
        self.assertIsNone(start_redirect("127.0.0.1", 8080, 80))        # dashboard only on this PC: no redirect
        self.assertIsNone(start_redirect("0.0.0.0", 8080, 0))           # HTTP_REDIRECT empty: off
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            free = s.getsockname()[1]
        srv = start_redirect("0.0.0.0", 8080, free)
        self.assertIsNotNone(srv)
        try:
            c = http.client.HTTPConnection("127.0.0.1", free, timeout=5)
            c.request("GET", "/", headers={"Host": "ninjadash.local"})
            r = c.getresponse()
            self.assertEqual(r.status, 302)
            self.assertEqual(r.getheader("Location"), "http://ninjadash.local:8080/")
            c.close()
        finally:
            srv.shutdown()
            srv.server_close()

    def test_setting(self):
        from ninjadash.config import _port
        self.assertEqual(_port("80"), 80)
        self.assertEqual(_port(""), 0)
        self.assertEqual(_port("off"), 0)
        self.assertEqual(_port("70000"), 0)
