"""Example data, used until an API client is configured (or with DEMO=1). Names are made up."""
from __future__ import annotations

import os

ORGS = {
    "Acme Logistics":   ["SRV-DC01", "SRV-DC02", "SRV-APP01", "SRV-APP02", "SRV-ERP01", "SRV-WEB01", "SRV-VEEAM", "HV-ACME01", "HV-ACME02", "SRV-RDS01", "SRV-FS01", "SRV-SQL01"],
    "Riverside Clinic": ["SRV-DC01", "SRV-DC02", "SRV-PACS01", "SRV-PACS02", "SRV-APP01", "SRV-APP02", "SRV-RDS01", "SRV-SQL02", "HV-HOST01", "HV-HOST03", "SRV-FS02", "SRV-RDS02", "HV-HOST02", "SRV-APP03"],
    "Northwind Dental": ["DC-01", "DC-02", "SRV-XRAY", "SRV-FS01", "SRV-APP01", "NAS-01"],
    "Brightline Legal": ["SRV-DC01", "SRV-DMS01", "SRV-FS01", "SRV-SQL01", "SRV-RDS01"],
    "Internal IT":      ["SRV-DC01", "SRV-RMM", "SRV-MON01", "SRV-FS01", "SRV-BKP01", "PVE-01", "SRV-PRINT"],
    "Harbor Café":      ["SRV-POS01", "NAS-01"],
}
M, H, D = 60, 3600, 86400


def demo_summary(now: float) -> dict:
    s = _typical(now)
    if os.environ.get("NINJADASH_DEMO_SCENARIO") == "busy":      # stress test for the layout fitting
        extra = [("SRV-PACS01", "Riverside Clinic", "hardware", "RAID 1 degraded · disk 0 failed"),
                 ("SRV-DMS01", "Brightline Legal", "backup", "Backup failed 3× · VSS error"),
                 ("HV-ACME01", "Acme Logistics", "hardware", "Fan 2 failed"),
                 ("SRV-MON01", "Internal IT", "antivirus", "Antivirus definitions out of date"),
                 ("SRV-XRAY", "Northwind Dental", "hardware", "SMART: drive failure predicted"),
                 ("SRV-POS01", "Harbor Café", "backup", "No successful backup for 5 days"),
                 ("SRV-WEB01", "Acme Logistics", "offline", "Not responding"),
                 ("SRV-ERP01", "Acme Logistics", "hardware", "Memory errors logged (WHEA)"),
                 ("NAS-01", "Northwind Dental", "hardware", "Synology: Volume 1 degraded"),
                 ("SRV-RMM", "Internal IT", "backup", "Backup repository 97 % full")]
        for i, (n, o, c, t) in enumerate(extra):
            s["affected"].append({"name": n, "org": o, "state": "offline" if c == "offline" else ("critical" if i % 2 == 0 else "warning"),
                                  "issues": [{"category": c, "severity": "critical", "text": t, "since": now - (i + 1) * 1800}]})
        taken = {(a["org"], a["name"]) for a in s["affected"]}
        s["healthy"] = [h for h in s["healthy"] if (h["org"], h["name"]) not in taken]
        s["workstations"] = (s["workstations"] * 2)[:10]
        s["workstationTotal"] = 23
    return s


def _typical(now: float) -> dict:
    def iss(cat, sev, text, ago):
        return {"category": cat, "severity": sev, "text": text, "since": now - ago}

    affected = [
        {"name": "SRV-FS01", "org": "Acme Logistics", "state": "critical", "issues": [iss("hardware", "critical", "RAID 5 degraded · disk 2 failed", 3 * H)]},
        {"name": "SRV-RDS02", "org": "Riverside Clinic", "state": "critical", "issues": [iss("antivirus", "critical", "Active threat: Trojan.Win64.Agent", 22 * M)]},
        {"name": "SRV-SQL01", "org": "Acme Logistics", "state": "critical", "issues": [
            iss("backup", "critical", "Backup failed 2× · last good 38 h ago", 14 * H),
            iss("hardware", "warning", "SMART: reallocated sectors rising", 2 * D)]},
        {"name": "SRV-PRINT", "org": "Internal IT", "state": "offline", "issues": [iss("offline", "offline", "Not responding", 47 * M)]},
        {"name": "HV-HOST02", "org": "Riverside Clinic", "state": "warning", "issues": [iss("hardware", "warning", "PSU 2 failed · redundancy lost", 6 * H)]},
        {"name": "SRV-APP03", "org": "Riverside Clinic", "state": "warning", "issues": [iss("backup", "warning", "No successful backup for 3 days", 3 * D)]},
    ]
    taken = {(s["org"], s["name"]) for s in affected}
    healthy = [{"name": n, "org": o} for o, names in ORGS.items() for n in names if (o, n) not in taken]
    ws = [
        dict(iss("hardware", "critical", "SMART: drive failure predicted", 2 * H), device="WS-114", org="Riverside Clinic"),
        dict(iss("antivirus", "critical", "Antivirus disabled", 1 * D), device="LT-SALES-07", org="Acme Logistics"),
        dict(iss("antivirus", "warning", "Threat quarantined: PUA.Bundler", 3 * H), device="WS-RECEPTION", org="Harbor Café"),
        dict(iss("hardware", "warning", "Memory errors logged (WHEA)", 5 * H), device="WS-022", org="Brightline Legal"),
        dict(iss("backup", "warning", "Backup failed", 14 * H), device="WS-PRAXIS-03", org="Northwind Dental"),
        dict(iss("hardware", "minor", "Battery health 41 %", 6 * D), device="LT-JLEE", org="Brightline Legal"),
    ]
    return {
        "orgCount": len(ORGS),
        "online": {"servers": [45, 46], "workstations": [356, 392]},
        "pillars": {
            "hardware": {"servers": 3, "workstations": 3, "state": "critical", "open": 7, "note": "RAID · SMART · PSU"},
            "backup": {"servers": 2, "workstations": 1, "state": "critical", "open": 3, "note": "131 of 134 jobs OK · 24 h"},
            "antivirus": {"servers": 1, "workstations": 2, "state": "critical", "open": 3, "note": "1 active · 1 quarantined"},
        },
        "affected": affected,
        "healthy": healthy,
        "workstations": ws,
        "workstationTotal": len(ws),
        "trend": {
            "hardware": [1, 0, 2, 1, 0, 0, 1, 3, 1, 0, 2, 1, 2, 3],
            "backup": [0, 1, 0, 0, 2, 0, 0, 1, 0, 0, 1, 0, 2, 1],
            "antivirus": [0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 2],
        },
        "ignoredDevices": 0,
        "updates": {
            "os": {"approval": 312, "queued": 41, "failed": 3, "approvalDevices": 214, "approvalServers": 12, "queuedDevices": 29, "failedDevices": 3, "top": [
                {"name": "2026-11 Cumulative Update for Windows Server 2022 (KB5049983)", "devices": 12, "servers": 12, "severity": "critical"},
                {"name": "2026-11 Cumulative Update for Windows 11 24H2 (KB5049981)", "devices": 168, "servers": 0, "severity": "critical"},
                {"name": "2026-11 .NET Framework 4.8.1 Update (KB5049620)", "devices": 131, "servers": 9, "severity": "important"},
                {"name": "Microsoft Defender Antivirus platform update", "devices": 22, "servers": 0, "severity": "moderate"},
            ]},
            "apps": {"approval": 57, "queued": 12, "failed": 1, "approvalDevices": 49, "approvalServers": 3, "queuedDevices": 10, "failedDevices": 1, "top": [
                {"name": "Google Chrome 156.0.8078.79", "devices": 31, "servers": 0, "severity": "critical"},
                {"name": "Adobe Acrobat Reader 25.001.20756", "devices": 14, "servers": 0, "severity": "important"},
                {"name": "7-Zip 26.00", "devices": 9, "servers": 3, "severity": "moderate"},
                {"name": "Notepad++ 8.8.7", "devices": 6, "servers": 2, "severity": "low"},
            ]},
            "storage": {"total": 5, "critical": 2, "servers": 3, "warnPercent": 90, "items": [
                {"device": "SRV-FS01", "org": "Acme Logistics", "tier": "server", "volume": "D:", "label": "Data", "usedPct": 96.4, "free": 72e9, "capacity": 2e12, "severity": "critical"},
                {"device": "DC-02", "org": "Northwind Dental", "tier": "server", "volume": "C:", "label": "", "usedPct": 95.1, "free": 4.9e9, "capacity": 100e9, "severity": "critical"},
                {"device": "SRV-SQL02", "org": "Riverside Clinic", "tier": "server", "volume": "L:", "label": "Logs", "usedPct": 91.8, "free": 41e9, "capacity": 500e9, "severity": "warning"},
                {"device": "WS-RECEPTION", "org": "Harbor Café", "tier": "workstation", "volume": "C:", "label": "", "usedPct": 93.0, "free": 16.8e9, "capacity": 240e9, "severity": "warning"},
                {"device": "LT-SALES-07", "org": "Acme Logistics", "tier": "workstation", "volume": "C:", "label": "", "usedPct": 90.4, "free": 24e9, "capacity": 250e9, "severity": "warning"},
            ]},
        },
    }
