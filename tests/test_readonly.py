"""NinjaOne access must be read-only, plus the patch/storage panel, the theme switch and the pointer helper."""
import importlib.util
import json
import os
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tests"))

import fake_ninja  # noqa: E402
from ninjadash.ninja import NinjaClient  # noqa: E402


def make_app(extra_env: str = ""):
    from ninjadash.app import App
    from ninjadash.config import load_config
    tmp = tempfile.mkdtemp()
    env = Path(tmp, "x.env")
    env.write_text(extra_env + f"\nHISTORY_DB={tmp}/h.sqlite\n")
    os.environ["NINJADASH_ENV"] = str(env)
    try:
        return App(load_config())
    finally:
        del os.environ["NINJADASH_ENV"]


class ReadOnlyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = ThreadingHTTPServer(("127.0.0.1", 0), fake_ninja.H)
        threading.Thread(target=cls.fake.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.fake.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.fake.shutdown()

    def test_full_sync_only_reads(self):
        fake_ninja.REQUESTS.clear()
        app = make_app(f"NINJA_BASE_URL={self.base}\nNINJA_CLIENT_ID=x\nNINJA_CLIENT_SECRET=test-secret\nNINJA_SCOPE=management")
        app.poll_once()
        methods = {(m, p) for m, p in fake_ninja.REQUESTS}
        writes = {(m, p) for m, p in methods if m != "GET"}
        self.assertEqual(writes, {("POST", "/ws/oauth/token")}, "only the login may be a non-GET request")
        self.assertTrue(all(p.startswith("/v2/") for m, p in methods if m == "GET"))
        self.assertGreaterEqual(len(methods), 9)                   # devices, alerts, AV, patches, volumes, ...
        self.assertEqual(app.client.scope, "monitoring")            # NINJA_SCOPE=management is ignored

    def test_login_asks_monitoring_scope_only(self):
        seen = {}
        orig = urllib.request.urlopen

        def spy(req, *a, **k):
            if getattr(req, "data", None):
                seen["body"] = req.data.decode()
            return orig(req, *a, **k)
        urllib.request.urlopen = spy
        try:
            NinjaClient(self.base, "x", "test-secret", scope="management control")._fetch_token()
        finally:
            urllib.request.urlopen = orig
        self.assertIn("scope=monitoring", seen["body"])
        self.assertNotIn("management", seen["body"])

    def test_client_refuses_paths_outside_v2(self):
        c = NinjaClient(self.base, "x", "test-secret")
        for bad in ("/ws/oauth/token", "/api/v2/device/1/reboot", "/v2/../ws/x"):
            with self.assertRaises(ValueError):
                c.get(bad)

    def test_no_write_methods_in_client_code(self):
        src = (ROOT / "backend/ninjadash/ninja.py").read_text()
        for verb in ("PUT", "PATCH", "DELETE"):
            self.assertNotIn(f'method="{verb}"', src)
        self.assertEqual(src.count('method="POST"'), 1)             # the login


class UpdatesPanelTest(unittest.TestCase):
    def setUp(self):
        from ninjadash.classify import Classifier
        from ninjadash.config import DEFAULT_RULES, load_rules
        from ninjadash.summary import Snapshot, build_summary
        snap = Snapshot(orgs=fake_ninja.ORGS, devices=fake_ninja.DEVICES, alerts=[],
                        os_patches=fake_ninja.OS_PATCHES, sw_patches=fake_ninja.SW_PATCHES, volumes=fake_ninja.VOLUMES)
        self.u = build_summary(snap, Classifier(load_rules(DEFAULT_RULES)), None, time.time())["updates"]

    def test_os_patches(self):
        os_ = self.u["os"]
        self.assertEqual((os_["approval"], os_["queued"], os_["failed"]), (4, 1, 1))
        self.assertEqual((os_["approvalDevices"], os_["approvalServers"]), (4, 2))
        self.assertEqual(os_["top"][0]["name"], "2026-11 Cumulative Update for Windows Server 2022")   # servers first
        self.assertEqual(os_["top"][0]["servers"], 2)

    def test_app_patches(self):
        apps = self.u["apps"]
        self.assertEqual((apps["approval"], apps["queued"]), (3, 1))
        names = [t["name"] for t in apps["top"]]
        self.assertEqual(names[0], "7-Zip 26.00")                    # on a server, so it comes first
        self.assertIn("Google Chrome 156", names)

    def test_storage(self):
        st = self.u["storage"]
        self.assertEqual(st["total"], 3)                             # recovery, removable and roomy volumes skipped
        self.assertEqual(st["critical"], 1)
        first = st["items"][0]
        self.assertEqual((first["device"], first["volume"], first["severity"]), ("SRV-FS01", "D:", "critical"))
        self.assertEqual(st["items"][-1]["tier"], "workstation")      # servers listed first

    def test_missing_endpoints_give_none(self):
        from ninjadash.classify import Classifier
        from ninjadash.config import DEFAULT_RULES, load_rules
        from ninjadash.summary import Snapshot, build_summary
        u = build_summary(Snapshot(devices=fake_ninja.DEVICES), Classifier(load_rules(DEFAULT_RULES)), None, time.time())["updates"]
        self.assertEqual(u, {"os": None, "apps": None, "storage": None})


class ThemeTest(unittest.TestCase):
    def test_modes_and_persistence(self):
        app = make_app("THEME=auto\nLIGHT_FROM=00:00\nLIGHT_UNTIL=23:59")
        self.assertEqual(app.theme()["mode"], "auto")
        self.assertEqual(app.set_theme("dark")["effective"], "dark")
        self.assertEqual(app.set_theme("off")["effective"], "light")        # HA switch "dark mode" off
        self.assertEqual(app.set_theme("toggle")["effective"], "dark")
        saved = json.loads(app.state_file.read_text())
        self.assertEqual(saved["theme"], "dark")
        with self.assertRaises(ValueError):
            app.set_theme("purple")

    def test_theme_api(self):
        from ninjadash.server import Server, make_handler, check_access
        app = make_app("SCREEN_TOKEN=tok")
        httpd = Server(("127.0.0.1", 0), make_handler(app, ROOT / "frontend"))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            def post(path, body=None):
                r = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(), method="POST")
                with urllib.request.urlopen(r, timeout=5) as resp:
                    return json.load(resp)
            self.assertEqual(post("/api/theme", {"mode": "light"})["effective"], "light")
            self.assertEqual(post("/api/theme/dark")["effective"], "dark")
            with urllib.request.urlopen(base + "/api/screen", timeout=5) as resp:
                self.assertEqual(json.load(resp)["theme"], "dark")          # the kiosk page follows this
        finally:
            httpd.shutdown()
        self.assertEqual(check_access("/api/theme", "POST", False, "screen", "tok", None, None)[0], 401)
        self.assertEqual(check_access("/api/theme", "POST", False, "screen", "tok", "Bearer tok", None)[0], 200)


class PointerNudgeTest(unittest.TestCase):
    def test_kernel_struct_layout(self):
        spec = importlib.util.spec_from_file_location("nudge", ROOT / "deploy/kiosk/pointer-nudge.py")
        nudge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nudge)
        self.assertEqual(len(nudge.setup_struct()), 92)               # sizeof(struct uinput_setup)
        self.assertEqual(len(nudge.event(2, 0, 1)), 24)               # sizeof(struct input_event), 64-bit
        self.assertEqual(struct.unpack("llHHi", nudge.event(2, 0, -2))[2:], (2, 0, -2))
        self.assertEqual((nudge.UI_DEV_SETUP, nudge.UI_SET_RELBIT), (0x405C5503, 0x40045566))


if __name__ == "__main__":
    unittest.main()
