"""Turns raw NinjaOne data into the one JSON document the dashboard draws (same shape as the mockup)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .classify import CATEGORIES, SEV_RANK, Classifier

WS_LIMIT = 6


@dataclass
class Snapshot:
    orgs: list = field(default_factory=list)
    devices: list = field(default_factory=list)
    alerts: list = field(default_factory=list)
    av_status: list | None = None        # None = endpoint not available
    av_threats: list | None = None
    backup_jobs: list | None = None
    os_patches: list | None = None       # /v2/queries/os-patches
    sw_patches: list | None = None       # /v2/queries/software-patches (third-party apps)
    volumes: list | None = None          # /v2/queries/volumes


@dataclass
class Issue:
    device_id: int
    category: str          # hardware | backup | antivirus | offline | other
    severity: str          # critical | warning | minor | offline
    text: str
    since: float | None
    key: str


# ---- field helpers: NinjaOne field names vary between endpoints and versions ----
def first(d: dict, *keys, default=None):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return default


def to_epoch(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        v = float(v)
        return v / 1000 if v > 1e12 else v
    if isinstance(v, str):
        try:
            return float(v) / (1000 if float(v) > 1e12 else 1)
        except ValueError:
            pass
        try:
            return dt.datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def short(text: str, limit: int = 110) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def device_name(d: dict) -> str:
    return str(first(d, "displayName", "systemName", "dnsName", "netbiosName", default=f"Device {d.get('id')}"))


def worst(sevs) -> str:
    sevs = list(sevs)
    return min(sevs, key=lambda s: SEV_RANK.get(s, 9)) if sevs else "ok"


def chip_state(sev: str) -> str:
    return {"minor": "warning"}.get(sev, sev)


# ---- issue extraction --------------------------------------------------------
def alert_issues(snap: Snapshot, clf: Classifier, devices: dict) -> list[Issue]:
    out = []
    for a in snap.alerts:
        dev_id = first(a, "deviceId", "nodeId")
        dev = devices.get(dev_id)
        if not dev or not dev["tier"]:
            continue
        subject = first(a, "subject", default="")
        message = first(a, "message", default="")
        src = a.get("sourceConfig") if isinstance(a.get("sourceConfig"), dict) else {}
        conditions = [str(x) for x in (a.get("sourceName"), a.get("conditionName"), a.get("sourceConfigName"),
                                        src.get("name"), subject) if x]
        text_for_match = f"{subject} {message} {' '.join(conditions)}"
        category, rule = clf.category(conditions, text_for_match, dev["name"])
        severity = (rule or {}).get("severity") or clf.severity(a.get("severity"), a.get("priority"))
        if category == "other" and not (dev["tier"] == "server" and clf.shows_other(severity)):
            continue
        message_line = next((ln for ln in str(message).splitlines() if ln.strip()), "")
        label = subject or message_line or first(a, "sourceName", default="Alert")
        out.append(Issue(dev_id, category, severity, short(label), to_epoch(first(a, "createTime", "activityTime", "updateTime")),
                         f"alert:{first(a, 'uid', 'id', default=label)}"))
    return out


def antivirus_issues(snap: Snapshot, clf: Classifier, devices: dict, now: float) -> list[Issue]:
    out = []
    q_hours = float(clf.display.get("quarantine_hours", 24))
    resolved = ("QUARANTIN", "REMOVED", "RESOLVED", "CLEAN", "DELETED", "BLOCKED", "ALLOWED", "RESTORED", "IGNORED")
    for t in snap.av_threats or []:
        dev_id = first(t, "deviceId", "nodeId")
        if dev_id not in devices or not devices[dev_id]["tier"]:
            continue
        name = short(first(t, "name", "threatName", "threat", "description", default="unknown threat"), 70)
        status = str(first(t, "status", "threatStatus", "state", default="")).upper()
        when = to_epoch(first(t, "timestamp", "detectedTime", "detectionTime", "time", "createTime"))
        if "QUARANTIN" in status:
            if when and now - when <= q_hours * 3600:
                out.append(Issue(dev_id, "antivirus", "warning", f"Threat quarantined: {name}", when, f"threat:{dev_id}:{name}:{when}"))
        elif not any(r in status for r in resolved):
            out.append(Issue(dev_id, "antivirus", "critical", f"Active threat: {name}", when, f"threat:{dev_id}:{name}:{when}"))

    per_device: dict = {}
    for s in snap.av_status or []:
        dev_id = first(s, "deviceId", "nodeId")
        if dev_id in devices and devices[dev_id]["tier"]:
            per_device.setdefault(dev_id, []).append(s)
    for dev_id, products in per_device.items():
        states = [str(first(p, "productState", "state", "status", default="")).upper() for p in products]
        if states and not any(st in ("ON", "ENABLED", "RUNNING", "ACTIVE", "") for st in states):
            prod = first(products[0], "productName", "name", default="Antivirus")
            out.append(Issue(dev_id, "antivirus", "critical", f"Antivirus disabled ({short(prod, 40)})", None, f"avoff:{dev_id}"))
            continue
        defs = [str(first(p, "definitionStatus", "definitionsStatus", "definitionState", default="")).upper() for p in products]
        if defs and all(("OUT" in d or "EXPIRED" in d or "OLD" in d) for d in defs if d) and any(defs):
            out.append(Issue(dev_id, "antivirus", "warning", "Antivirus definitions out of date", None, f"avdefs:{dev_id}"))
    return out


def backup_issues(snap: Snapshot, clf: Classifier, devices: dict, now: float) -> tuple[list[Issue], dict | None]:
    if snap.backup_jobs is None:
        return [], None
    window = float(clf.display.get("backup_window_hours", 24)) * 3600
    ok = total = 0
    failures: dict = {}
    for j in snap.backup_jobs:
        start = to_epoch(first(j, "jobStartTime", "startTime", "jobEndTime", "endTime", "createTime"))
        if start is None or now - start > window:
            continue
        status = str(first(j, "jobStatus", "status", "state", default="")).upper()
        if status in ("PROCESSING", "RUNNING", "IN_PROGRESS", "QUEUED", "STARTED"):
            continue
        total += 1
        if "FAIL" in status or "ERROR" in status:
            dev_id = first(j, "deviceId", "nodeId")
            failures.setdefault(dev_id, []).append((start, short(first(j, "planName", "jobName", "name", default=""), 40)))
        else:
            ok += 1
    out = []
    for dev_id, fails in failures.items():
        if dev_id not in devices or not devices[dev_id]["tier"]:
            continue
        fails.sort()
        n = len(fails)
        plan = fails[-1][1]
        text = f"Backup failed{f' {n}×' if n > 1 else ''}{f' · {plan}' if plan else ''}"
        out.append(Issue(dev_id, "backup", "critical" if n > 1 else "warning", text, fails[0][0], f"backup:{dev_id}:{int(fails[0][0])}"))
    return out, {"ok": ok, "total": total}


def offline_issues(clf: Classifier, devices: dict, now: float) -> list[Issue]:
    limit = float(clf.display.get("offline_server_minutes", 15)) * 60
    out = []
    for dev_id, d in devices.items():
        if d["tier"] == "server" and d["offline"]:
            last = d["last_contact"]
            if last is None or now - last >= limit:
                out.append(Issue(dev_id, "offline", "offline", "Not responding", last, f"offline:{dev_id}:{int(last or 0)}"))
    return out


# ---- patches waiting for approval / queued, and low storage ------------------------
APPROVAL_WORDS = ("PENDING", "MANUAL", "AWAIT", "NEEDS_APPROVAL", "NOT_APPROVED", "REQUIRES_APPROVAL", "APPROVAL")
QUEUED_WORDS = ("APPROVED", "QUEUED", "SCHEDULED", "DOWNLOAD", "INSTALLING", "STAGED")
SEVERITY_ORDER = {"critical": 0, "important": 1, "high": 1, "moderate": 2, "medium": 2, "low": 3, "optional": 4}


def patch_state(p: dict) -> str | None:
    s = str(first(p, "status", "patchStatus", "approvalStatus", "state", default="")).upper()
    if "FAIL" in s:
        return "failed"
    if "REJECT" in s or s in ("INSTALLED", "SUPERSEDED", "NOT_APPLICABLE"):
        return None
    if any(w in s for w in QUEUED_WORDS) and "NOT_APPROVED" not in s:
        return "queued"
    if any(w in s for w in APPROVAL_WORDS):
        return "approval"
    return None


def patch_block(rows: list | None, devices: dict) -> dict | None:
    if rows is None:
        return None
    counts = {"approval": 0, "queued": 0, "failed": 0}
    approval_devices: set = set()
    groups: dict = {}
    for p in rows:
        dev_id = first(p, "deviceId", "nodeId")
        dev = devices.get(dev_id)
        if not dev or not dev["tier"]:
            continue
        state = patch_state(p)
        if not state:
            continue
        counts[state] += 1
        if state != "approval":
            continue
        approval_devices.add(dev_id)
        name = short(first(p, "name", "title", "kbNumber", "productIdentifier", "displayName", default="Update"), 80)
        g = groups.setdefault(name, {"name": name, "devices": set(), "servers": set(), "severity": ""})
        g["devices"].add(dev_id)
        if dev["tier"] == "server":
            g["servers"].add(dev_id)
        sev = str(first(p, "severity", "impact", "classification", default="")).lower()
        if sev and SEVERITY_ORDER.get(sev, 9) < SEVERITY_ORDER.get(g["severity"], 9):
            g["severity"] = sev
    top = sorted(groups.values(), key=lambda g: (-len(g["servers"]), -len(g["devices"]), SEVERITY_ORDER.get(g["severity"], 9), g["name"]))
    return {
        **counts,
        "approvalDevices": len(approval_devices),
        "approvalServers": len({d for d in approval_devices if devices[d]["tier"] == "server"}),
        "top": [{"name": g["name"], "devices": len(g["devices"]), "servers": len(g["servers"]), "severity": g["severity"]}
                for g in top[:8]],
    }


def storage_block(rows: list | None, clf: Classifier, devices: dict) -> dict | None:
    if rows is None:
        return None
    warn = float(clf.display.get("storage_warn_percent", 90))
    crit = float(clf.display.get("storage_critical_percent", 95))
    min_bytes = float(clf.display.get("storage_min_gb", 2)) * 1024 ** 3
    skip_words = ("recovery", "efi", "system reserved", "boot", "swap")
    items = []
    for v in rows:
        dev = devices.get(first(v, "deviceId", "nodeId"))
        if not dev or not dev["tier"]:
            continue
        try:
            cap = float(first(v, "capacity", "size", "totalSpace", "totalSize"))
            free = float(first(v, "freeSpace", "free", "availableSpace", "freeSize"))
        except (TypeError, ValueError):
            continue
        if cap < min_bytes or free < 0 or free > cap:
            continue
        kind = str(first(v, "deviceType", "driveType", "type", default="")).lower()
        if any(k in kind for k in ("removable", "cd", "optical", "network", "ram")):
            continue
        name = str(first(v, "name", "driveLetter", "mountPoint", "path", default="")).rstrip("\\") or "volume"
        label = str(first(v, "label", "volumeName", default=""))
        if any(w in f"{name} {label}".lower() for w in skip_words):
            continue
        used = 100.0 * (1 - free / cap)
        if used >= warn:
            items.append({"device": dev["name"], "org": dev["org"], "tier": dev["tier"], "volume": name,
                          "label": label, "usedPct": round(used, 1), "free": free, "capacity": cap,
                          "severity": "critical" if used >= crit else "warning"})
    items.sort(key=lambda i: (i["tier"] != "server", -i["usedPct"]))
    return {"total": len(items), "critical": sum(1 for i in items if i["severity"] == "critical"),
            "servers": sum(1 for i in items if i["tier"] == "server"), "items": items[:10],
            "warnPercent": warn}


# ---- the summary --------------------------------------------------------------
def build_summary(snap: Snapshot, clf: Classifier, history, now: float) -> dict:
    orgs = {o.get("id"): str(o.get("name", "")) for o in snap.orgs}
    devices = {}
    for d in snap.devices:
        name = device_name(d)
        org_ref = (d.get("references") or {}).get("organization") or {}
        devices[d.get("id")] = {
            "name": name,
            "org": orgs.get(d.get("organizationId")) or org_ref.get("name") or "",
            "tier": clf.tier(str(d.get("nodeClass", "")), name),
            "offline": bool(d.get("offline")),
            "last_contact": to_epoch(first(d, "lastContact", "lastUpdate")),
        }

    issues = alert_issues(snap, clf, devices)
    issues += antivirus_issues(snap, clf, devices, now)
    b_issues, backup_stats = backup_issues(snap, clf, devices, now)
    issues += b_issues
    issues += offline_issues(clf, devices, now)

    seen, unique = set(), []
    for i in sorted(issues, key=lambda i: (SEV_RANK.get(i.severity, 9), -(i.since or 0))):
        k = (i.device_id, i.category, i.text.lower())
        if k not in seen:
            seen.add(k)
            unique.append(i)
    issues = unique

    if history is not None:
        history.record([(i.key, i.category) for i in issues])

    by_device: dict = {}
    for i in issues:
        by_device.setdefault(i.device_id, []).append(i)

    def issue_json(i: Issue) -> dict:
        return {"category": i.category, "severity": i.severity, "text": i.text, "since": i.since}

    servers = {k: v for k, v in devices.items() if v["tier"] == "server"}
    workstations = {k: v for k, v in devices.items() if v["tier"] == "workstation"}

    affected = []
    for dev_id, d in servers.items():
        its = by_device.get(dev_id)
        if its:
            sev = worst(i.severity for i in its)
            affected.append({"name": d["name"], "org": d["org"], "state": chip_state(sev),
                             "issues": [issue_json(i) for i in its], "_rank": SEV_RANK.get(sev, 9),
                             "_newest": max((i.since or 0) for i in its)})
    affected.sort(key=lambda s: (s["_rank"], -s["_newest"], s["name"]))
    for s in affected:
        s.pop("_rank"), s.pop("_newest")
    healthy = sorted(({"name": d["name"], "org": d["org"]} for k, d in servers.items() if k not in by_device),
                     key=lambda s: (s["org"].lower(), s["name"].lower()))

    ws_issues = [dict(issue_json(i), device=devices[i.device_id]["name"], org=devices[i.device_id]["org"])
                 for i in issues if i.device_id in workstations and i.category in CATEGORIES]

    pillars = {}
    for cat in CATEGORIES:
        cat_issues = [i for i in issues if i.category == cat]
        pillars[cat] = {
            "servers": len({i.device_id for i in cat_issues if i.device_id in servers}),
            "workstations": len({i.device_id for i in cat_issues if i.device_id in workstations}),
            "state": chip_state(worst(i.severity for i in cat_issues)),
            "open": len(cat_issues),
        }
    threats = [i for i in issues if i.category == "antivirus"]
    pillars["hardware"]["note"] = f"{pillars['hardware']['open']} open {'alert' if pillars['hardware']['open'] == 1 else 'alerts'}" if pillars["hardware"]["open"] else "No hardware alerts"
    if backup_stats and backup_stats["total"]:
        pillars["backup"]["note"] = f"{backup_stats['ok']} of {backup_stats['total']} jobs OK · 24 h"
    else:
        pillars["backup"]["note"] = "from NinjaOne alerts" if snap.backup_jobs is None else "no jobs in the last 24 h"
    if snap.av_threats is not None or snap.av_status is not None:
        active = sum(1 for i in threats if i.text.startswith("Active threat"))
        quarantined = sum(1 for i in threats if i.text.startswith("Threat quarantined"))
        pillars["antivirus"]["note"] = f"{active} active · {quarantined} quarantined"
    else:
        pillars["antivirus"]["note"] = "from NinjaOne alerts"

    def online(group):
        return [sum(1 for d in group.values() if not d["offline"]), len(group)]

    org_names = {d["org"] for d in devices.values() if d["tier"] and d["org"]}
    return {
        "orgCount": len(orgs) or len(org_names),
        "online": {"servers": online(servers), "workstations": online(workstations)},
        "pillars": pillars,
        "affected": affected,
        "healthy": healthy,
        "workstations": ws_issues[:WS_LIMIT],
        "workstationTotal": len(ws_issues),
        "trend": history.trend() if history is not None else {c: [0] * 14 for c in CATEGORIES},
        "updates": {
            "os": patch_block(snap.os_patches, devices),
            "apps": patch_block(snap.sw_patches, devices),
            "storage": storage_block(snap.volumes, clf, devices),
        },
        "ignoredDevices": sum(1 for d in devices.values() if not d["tier"]),
    }
