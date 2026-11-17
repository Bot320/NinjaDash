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

    def test_broken_optional_endpoint_does_not_stop_the_sync(self):
        import ninjadash.ninja as ninja_mod
        app = make_app(f"NINJA_BASE_URL={self.base}\nNINJA_CLIENT_ID=x\nNINJA_CLIENT_SECRET=test-secret")
        fake_ninja.BACKUP_CODE = 500                                 # NinjaOne answers 500 when Backup isn't used
        sleep, ninja_mod.time.sleep = ninja_mod.time.sleep, lambda s: None
        try:
            fake_ninja.REQUESTS.clear()
            app.poll_once()                                         # must not raise
            backup_calls = [p for m, p in fake_ninja.REQUESTS if p == "/v2/backup/jobs"]
            self.assertEqual(len(backup_calls), 2)                  # one retry, then skipped
            self.assertIsNone(app.error)
            self.assertIsNotNone(app.last_success)
            s = app.summary()
            self.assertGreater(len(s["affected"]), 0)
            self.assertIsNotNone(s["updates"]["os"])                # the other optional panels still load
            app._next_slow = 0
            fake_ninja.REQUESTS.clear()
            app.poll_once()
            self.assertNotIn("/v2/backup/jobs", [p for m, p in fake_ninja.REQUESTS])   # skipped for an hour
        finally:
            fake_ninja.BACKUP_CODE = 404
            ninja_mod.time.sleep = sleep

    def test_retry_error_names_the_status(self):
        import ninjadash.ninja as ninja_mod
        fake_ninja.BACKUP_CODE = 500
        sleep, ninja_mod.time.sleep = ninja_mod.time.sleep, lambda s: None
        try:
            with self.assertRaises(ninja_mod.NinjaError) as cm:
                NinjaClient(self.base, "x", "test-secret").backup_jobs(attempts=2)
        finally:
            fake_ninja.BACKUP_CODE = 404
            ninja_mod.time.sleep = sleep
        self.assertEqual(cm.exception.status, 500)
        self.assertIn("500", str(cm.exception))

    def test_manual_os_patches_asked_for_separately(self):
        c = NinjaClient(self.base, "x", "test-secret")
        fake_ninja.HIDE_MANUAL = True
        try:
            fake_ninja.REQUESTS.clear()
            rows = c.os_patches()
        finally:
            fake_ninja.HIDE_MANUAL = False
        self.assertEqual(sum(1 for r in rows if r["status"] == "MANUAL"), 2)   # found via ?status=MANUAL
        self.assertEqual(len(rows), len(fake_ninja.OS_PATCHES))                # all of them, no duplicates
        self.assertEqual([p for m, p in fake_ninja.REQUESTS].count("/v2/queries/os-patches"), 2)
        fake_ninja.REQUESTS.clear()
        c.os_patches()                                                          # MANUAL already in the list:
        self.assertEqual([p for m, p in fake_ninja.REQUESTS].count("/v2/queries/os-patches"), 1)   # one request

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

    def test_device_counts_per_state(self):
        os_ = self.u["os"]
        self.assertEqual((os_["queuedDevices"], os_["failedDevices"]), (1, 1))

    def test_ninjaone_status_values(self):
        from ninjadash.summary import patch_state
        self.assertEqual(patch_state({"status": "MANUAL"}), "approval")
        self.assertEqual(patch_state({"status": "APPROVED"}), "queued")
        self.assertEqual(patch_state({"status": "FAILED"}), "failed")
        self.assertIsNone(patch_state({"status": "REJECTED"}))
        for waiting in ("UNAPPROVED", "NOT_APPROVED", "Pending approval", "AWAITING_APPROVAL"):
            self.assertEqual(patch_state({"status": waiting}), "approval", waiting)

    def test_waiting_patches_count_as_needing_approval(self):
        from ninjadash.summary import patch_block, patch_reason, patch_state, pending_signal
        now = 1_800_000_000
        day = 86400
        # shapes a waiting patch may have; NinjaOne's real field is confirmed with `ninjadash patches`
        self.assertEqual(pending_signal({"status": "APPROVED", "approveAfter": (now + 2 * day) * 1000}, now)[:2], (True, now + 2 * day))
        self.assertEqual(pending_signal({"status": "APPROVED", "approvalDelayDays": 7, "releaseDate": now - 2 * day}, now)[:2],
                         (True, now + 5 * day))
        self.assertFalse(pending_signal({"status": "APPROVED", "approvalDelayDays": 7, "releaseDate": now - 9 * day}, now)[0])
        self.assertTrue(pending_signal({"status": "DELAYED"}, now)[0])
        self.assertTrue(pending_signal({"status": "PENDING", "delayed": True}, now)[0])
        self.assertFalse(pending_signal({"status": "APPROVED", "delayed": False, "timestamp": now}, now)[0])
        self.assertFalse(pending_signal({"status": "APPROVED", "approveAfter": now - day}, now)[0])    # date has passed
        self.assertEqual(patch_state({"status": "APPROVED", "approveAfter": now + day}, now), "approval")
        self.assertEqual(patch_state({"status": "FAILED", "delayed": True}, now), "failed")
        self.assertEqual(patch_reason({"status": "APPROVED", "approveAfter": now + day}, now), "field approveAfter (future date)")
        self.assertEqual(patch_reason({"status": "APPROVED"}, now), "status APPROVED")
        devices = {1: {"tier": "server"}, 2: {"tier": "workstation"}, 3: {"tier": "workstation"}}
        rows = [{"deviceId": 2, "name": "CU 11", "status": "APPROVED", "approveAfter": now + 3 * day},
                {"deviceId": 3, "name": "CU 11", "status": "APPROVED", "approveAfter": now + 2 * day},
                {"deviceId": 1, "name": "CU 2022", "status": "APPROVED"},
                {"deviceId": 1, "name": "SSU", "status": "MANUAL"}]
        b = patch_block(rows, devices, now)
        self.assertEqual((b["approval"], b["approvalDevices"], b["queued"]), (3, 3, 1))     # like NinjaOne's "needs approval"
        self.assertEqual((b["autoApprove"], b["autoApproveNext"]), (2, now + 2 * day))
        cu = next(t for t in b["top"] if t["name"] == "CU 11")
        self.assertEqual((cu["devices"], cu["auto"]), (2, now + 2 * day))
        self.assertIsNone(next(t for t in b["top"] if t["name"] == "SSU")["auto"])

    def test_rows_show_how_many_already_approved(self):
        from ninjadash.summary import patch_block
        devices = {i: {"tier": "workstation"} for i in range(1, 7)}
        rows = [{"deviceId": i, "name": "Preview CU", "status": "MANUAL"} for i in (1, 2, 3, 4)] + \
               [{"deviceId": i, "name": "Preview CU", "status": "APPROVED"} for i in (5, 6)] + \
               [{"deviceId": 1, "name": "Defender", "status": "MANUAL"}]
        top = {t["name"]: t for t in patch_block(rows, devices)["top"]}
        self.assertEqual((top["Preview CU"]["devices"], top["Preview CU"]["approved"]), (4, 2))
        self.assertEqual(top["Defender"]["approved"], 0)

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
