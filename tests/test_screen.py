"""Screen on/off API and the access rules for other computers (Home Assistant)."""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from ninjadash.server import check_access, is_local  # noqa: E402

TOKEN = "s3cret-token"


class AccessRulesTest(unittest.TestCase):
    def check(self, path, local=False, mode="screen", auth=None, q=None, token=TOKEN):
        return check_access(path, "GET", local, mode, token, auth, q)[0]

    def test_local_always_allowed(self):
        self.assertEqual(self.check("/api/summary", local=True, mode="none"), 200)
        self.assertEqual(self.check("/api/screen", local=True, token=""), 200)

    def test_remote_screen_mode(self):
        self.assertEqual(self.check("/api/summary"), 403)                      # dashboard data stays private
        self.assertEqual(self.check("/"), 403)
        self.assertEqual(self.check("/api/screen"), 401)                       # no token
        self.assertEqual(self.check("/api/screen", auth="Bearer wrong"), 401)
        self.assertEqual(self.check("/api/screen", auth=f"Bearer {TOKEN}"), 200)
        self.assertEqual(self.check("/api/screen/off", q=TOKEN), 200)
        self.assertEqual(self.check("/api/screen", auth=f"Bearer {TOKEN}", token=""), 403)   # token not set up

    def test_remote_other_modes(self):
        self.assertEqual(self.check("/api/screen", mode="none", auth=f"Bearer {TOKEN}"), 403)
        self.assertEqual(self.check("/api/summary", mode="all"), 200)
        self.assertEqual(self.check("/api/screen", mode="all"), 401)          # screen still needs the token

    def test_is_local(self):
        self.assertTrue(is_local("127.0.0.1"))
        self.assertTrue(is_local("::1"))
        self.assertTrue(is_local("::ffff:127.0.0.1"))
        self.assertFalse(is_local("192.168.1.20"))


class ScreenApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ninjadash.app import App
        from ninjadash.config import load_config
        from ninjadash.server import Server, make_handler
        tmp = tempfile.mkdtemp()
        env = Path(tmp, "x.env")
        env.write_text(f"NINJA_CLIENT_ID=\nNINJA_CLIENT_SECRET=\nHISTORY_DB={tmp}/h.sqlite\nSCREEN_TOKEN={TOKEN}\n")
        os.environ["NINJADASH_ENV"] = str(env)
        try:
            cls.app = App(load_config())
        finally:
            del os.environ["NINJADASH_ENV"]
        cls.httpd = Server(("127.0.0.1", 0), make_handler(cls.app, ROOT / "frontend"))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def req(self, path, body=None, method=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, method=method or ("POST" if data is not None else "GET"),
                                   headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=5) as resp:
            return json.load(resp)

    def test_switch_and_read(self):
        self.assertTrue(self.req("/api/screen")["on"])
        self.assertFalse(self.req("/api/screen", {"state": "off"})["on"])
        self.assertFalse(self.req("/api/summary")["screen"]["on"])
        self.assertTrue(self.req("/api/screen/on", method="POST")["on"])
        self.assertFalse(self.req("/api/screen/toggle", method="POST")["on"])
        self.assertTrue(self.req("/api/screen", {"state": True})["on"])
        self.assertFalse(self.req("/api/screen")["agent"])
        self.assertTrue(self.req("/api/screen?agent=1")["agent"])

    def test_bad_state(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.req("/api/screen", {"state": "dim"})
        self.assertEqual(cm.exception.code, 400)
        cm.exception.close()

    def test_page_has_initial_data_and_blackout(self):
        with urllib.request.urlopen(self.base + "/", timeout=5) as resp:
            html = resp.read().decode()
        self.assertIn("window.NINJADASH_INITIAL=", html)
        self.assertIn('class="blackout"', html)


if __name__ == "__main__":
    unittest.main()
