"""A fake NinjaOne API for local testing: `python3 tests/fake_ninja.py 9911`.

The field names follow NinjaOne's public API v2 as far as known; the real ones get confirmed
with `ninjadash check --fields` against a real account.
"""
from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

NOW = time.time()
ORGS = [{"id": 1, "name": "Acme Logistics"}, {"id": 2, "name": "Riverside Clinic"}, {"id": 3, "name": "Internal IT"}]


def dev(i, name, org, cls, offline=False, last=60):
    return {"id": i, "displayName": name, "systemName": name, "organizationId": org, "nodeClass": cls,
            "offline": offline, "lastContact": NOW - last}


DEVICES = [
    dev(1, "SRV-FS01", 1, "WINDOWS_SERVER"),
    dev(2, "SRV-VEEAM", 1, "WINDOWS_SERVER"),
    dev(3, "SRV-SQL01", 1, "WINDOWS_SERVER"),
    dev(4, "HV-HOST02", 2, "HYPERV_VMM_HOST"),
    dev(5, "SRV-RDS02", 2, "WINDOWS_SERVER"),
    dev(6, "SRV-PRINT", 3, "WINDOWS_SERVER", offline=True, last=47 * 60),
    dev(7, "NAS-01", 3, "NMS_NAS"),
    dev(8, "SRV-DC01", 1, "WINDOWS_SERVER"),
    dev(9, "SRV-DC01", 2, "WINDOWS_SERVER"),
    dev(10, "LNX-WEB01", 3, "LINUX_SERVER"),
    dev(11, "SRV-APP01", 2, "WINDOWS_SERVER", offline=True, last=5 * 60),   # offline only 5 min: not shown yet
    dev(20, "WS-114", 2, "WINDOWS_WORKSTATION"),
    dev(21, "LT-SALES-07", 1, "WINDOWS_WORKSTATION"),
    dev(22, "WS-RECEPTION", 2, "WINDOWS_WORKSTATION"),
    dev(23, "MBP-ANNA", 1, "MAC"),
    dev(24, "WS-OFFLINE", 1, "WINDOWS_WORKSTATION", offline=True, last=3 * 86400),
    dev(30, "VM-GUEST-1", 1, "VMWARE_VM_GUEST"),
] + [dev(100 + i, f"WS-{i:03d}", 1 + i % 3, "WINDOWS_WORKSTATION") for i in range(40)]


def alert(uid, device, severity, subject, source, ago, message=""):
    return {"uid": uid, "deviceId": device, "severity": severity, "priority": "HIGH", "subject": subject,
            "message": message or subject, "sourceType": "CONDITION", "sourceName": source, "createTime": NOW - ago}


ALERTS = [
    alert("a1", 1, "CRITICAL", "RAID 5 degraded - physical disk 2 failed", "Dell OMSA RAID health", 3 * 3600),
    alert("a2", 2, "MAJOR", "Veeam job 'Daily SQL' finished with Failed", "Veeam - job failed (event 190)", 14 * 3600),
    alert("a3", 3, "MODERATE", "SMART: reallocated sector count increasing on Disk 0", "Disk health", 2 * 86400),
    alert("a4", 4, "MODERATE", "Power supply 2 lost redundancy", "iDRAC event", 6 * 3600),
    alert("a5", 7, "CRITICAL", "Synology: Drive 3 in Volume 1 has failed", "NAS drive status (SNMP)", 40 * 60),
    alert("a6", 8, "CRITICAL", "CPU utilisation above 95 % for 15 minutes", "CPU", 20 * 60),           # other, critical, server -> shown
    alert("a7", 9, "MODERATE", "Disk C: is 91 % full", "Disk space", 2 * 3600),                       # other, warning -> hidden
    alert("a8", 20, "CRITICAL", "S.M.A.R.T. predicted failure on disk 0", "Disk health", 2 * 3600),
    alert("a9", 22, "MINOR", "Windows Update failed", "Patching", 5 * 3600),                          # other on workstation -> hidden
    alert("a10", 23, "MINOR", "Battery health 41 %", "Battery", 6 * 86400),
]

AV_THREATS = [
    {"deviceId": 5, "name": "Trojan:Win64/Agent.ABC", "status": "ACTIVE", "timestamp": NOW - 22 * 60},
    {"deviceId": 22, "name": "PUA:Win32/Bundler", "status": "QUARANTINED", "timestamp": NOW - 3 * 3600},
    {"deviceId": 20, "name": "Old.Thing", "status": "QUARANTINED", "timestamp": NOW - 9 * 86400},           # too old
]
AV_STATUS = [
    {"deviceId": 21, "productName": "Windows Defender", "productState": "OFF", "definitionStatus": "OUT_OF_DATE"},
    {"deviceId": 23, "productName": "Windows Defender", "productState": "OFF", "definitionStatus": "UP_TO_DATE"},
    {"deviceId": 23, "productName": "Bitdefender", "productState": "ON", "definitionStatus": "UP_TO_DATE"},   # passive Defender: fine
    {"deviceId": 1, "productName": "Windows Defender", "productState": "ON", "definitionStatus": "UP_TO_DATE"},
]


GB = 1024 ** 3
OS_PATCHES = [
    {"deviceId": 1, "name": "2026-11 Cumulative Update for Windows Server 2022", "severity": "CRITICAL", "status": "MANUAL"},
    {"deviceId": 3, "name": "2026-11 Cumulative Update for Windows Server 2022", "severity": "CRITICAL", "status": "MANUAL"},
    {"deviceId": 20, "name": "2026-11 Cumulative Update for Windows 11", "severity": "CRITICAL", "status": "PENDING"},
    {"deviceId": 21, "name": "2026-11 Cumulative Update for Windows 11", "severity": "CRITICAL", "status": "PENDING"},
    {"deviceId": 22, "name": "2026-11 Cumulative Update for Windows 11", "severity": "CRITICAL", "status": "APPROVED"},
    {"deviceId": 23, "name": "Old driver", "severity": "OPTIONAL", "status": "REJECTED"},
    {"deviceId": 20, "name": ".NET Framework update", "severity": "IMPORTANT", "status": "FAILED"},
]
SW_PATCHES = [
    {"deviceId": 20, "title": "Google Chrome 156", "impact": "critical", "status": "PENDING"},
    {"deviceId": 21, "title": "Google Chrome 156", "impact": "critical", "status": "PENDING"},
    {"deviceId": 2, "title": "7-Zip 26.00", "impact": "moderate", "status": "PENDING"},
    {"deviceId": 22, "title": "Zoom 7", "impact": "low", "status": "APPROVED"},
]
VOLUMES = [
    {"deviceId": 1, "name": "D:\\", "label": "Data", "capacity": 2000 * GB, "freeSpace": 70 * GB},      # 96.5 % -> critical
    {"deviceId": 9, "name": "C:\\", "label": "", "capacity": 100 * GB, "freeSpace": 9 * GB},            # 91 % -> warning
    {"deviceId": 1, "name": "C:\\", "label": "", "capacity": 120 * GB, "freeSpace": 60 * GB},           # fine
    {"deviceId": 3, "name": "\\\\?\\Volume{x}", "label": "Recovery", "capacity": 1 * GB, "freeSpace": 0.05 * GB},  # ignored
    {"deviceId": 20, "name": "C:\\", "label": "", "capacity": 240 * GB, "freeSpace": 20 * GB},          # 91.7 % workstation
    {"deviceId": 21, "name": "E:\\", "label": "USB", "deviceType": "Removable Disk", "capacity": 64 * GB, "freeSpace": 1 * GB},  # ignored
]
REQUESTS: list = []          # (method, path) of every request, for the read-only test


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _record(self):
        REQUESTS.append((self.command, urlparse(self.path).path))

    def do_PUT(self):
        self._record(); self._json(405, {})

    def do_PATCH(self):
        self._record(); self._json(405, {})

    def do_DELETE(self):
        self._record(); self._json(405, {})

    def _json(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        self._record()
        if self.path == "/ws/oauth/token":
            length = int(self.headers.get("Content-Length", 0))
            form = parse_qs(self.rfile.read(length).decode())
            if form.get("client_secret", [""])[0] != "test-secret":
                return self._json(401, {"error": "invalid_client"})
            return self._json(200, {"access_token": "tok", "expires_in": 3600, "token_type": "bearer"})
        self._json(404, {})

    def do_GET(self):
        self._record()
        if self.headers.get("Authorization") != "Bearer tok":
            return self._json(401, {"error": "unauthorized"})
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/v2/organizations":
            return self._json(200, ORGS)
        if u.path == "/v2/devices-detailed":
            size, after = int(q.get("pageSize", [500])[0]), int(q.get("after", [0])[0])
            page = [d for d in DEVICES if d["id"] > after][:size]
            return self._json(200, page)
        if u.path == "/v2/alerts":
            return self._json(200, ALERTS)
        if u.path == "/v2/queries/antivirus-threats":
            return self._json(200, {"cursor": None, "results": AV_THREATS})
        if u.path == "/v2/queries/antivirus-status":
            return self._json(200, {"cursor": None, "results": AV_STATUS})
        if u.path == "/v2/backup/jobs":
            return self._json(404, {"error": "Not licensed"})
        if u.path == "/v2/queries/os-patches":
            return self._json(200, {"cursor": None, "results": OS_PATCHES})
        if u.path == "/v2/queries/software-patches":
            return self._json(200, {"cursor": None, "results": SW_PATCHES})
        if u.path == "/v2/queries/volumes":
            return self._json(200, {"cursor": None, "results": VOLUMES})
        return self._json(404, {"error": "not found"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9911
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
