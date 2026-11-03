"""Example data, used until an API client is configured (or with DEMO=1). Names are made up."""
from __future__ import annotations

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
    }
