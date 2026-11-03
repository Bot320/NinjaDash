"""Decides a device's tier (server / workstation) and an alert's category and severity, from classify.toml."""
from __future__ import annotations

import fnmatch
import re

SEV_RANK = {"critical": 0, "offline": 1, "warning": 2, "minor": 3, "ok": 4, "none": 9}
CATEGORIES = ("hardware", "backup", "antivirus")
PRIORITY_FALLBACK = {"HIGH": "critical", "MEDIUM": "warning", "LOW": "minor", "NONE": "minor"}


def _glob_any(patterns, values) -> bool:
    for p in patterns:
        p = p.lower()
        for v in values:
            if v and fnmatch.fnmatchcase(v.lower(), p):
                return True
    return False


class Classifier:
    def __init__(self, rules: dict):
        self.severity_map = {k.upper(): v.lower() for k, v in rules.get("severity", {}).items()}
        tiers = rules.get("tiers", {})
        self.server_classes = tiers.get("server_classes", [])
        self.workstation_classes = tiers.get("workstation_classes", [])
        self.ignore_classes = tiers.get("ignore_classes", [])
        self.server_names = tiers.get("server_names", [])
        self.ignore_names = tiers.get("ignore_names", [])
        self.display = rules.get("display", {})
        self.rules = []
        for r in rules.get("rule", []):
            words = [w.lower() for w in r.get("text", [])]
            pattern = re.compile("|".join(r"(?<![a-z0-9])" + re.escape(w) for w in words)) if words else None
            self.rules.append({
                "name": r.get("name", r.get("category", "rule")),
                "condition": r.get("condition", []),
                "device": r.get("device", []),
                "text": pattern,
                "category": r.get("category", "other").lower(),
                "severity": (r.get("severity") or "").lower() or None,
                "tier": (r.get("tier") or "").lower() or None,
            })

    def tier(self, node_class: str, name: str) -> str | None:
        node_class = node_class or ""
        if _glob_any(self.ignore_names, [name]):
            return None
        if _glob_any(self.server_names, [name]):
            return "server"
        for r in self.rules:                                # a rule with only `device` + `tier` pins a tier
            if r["tier"] and r["device"] and not r["condition"] and not r["text"] and _glob_any(r["device"], [name]):
                return r["tier"]
        if _glob_any(self.ignore_classes, [node_class]):
            return None
        if _glob_any(self.server_classes, [node_class]):
            return "server"
        if _glob_any(self.workstation_classes, [node_class]):
            return "workstation"
        return None

    def severity(self, ninja_severity: str | None, priority: str | None = None) -> str:
        sev = (ninja_severity or "").upper()
        if sev in self.severity_map:
            return self.severity_map[sev]
        return PRIORITY_FALLBACK.get((priority or "").upper(), "warning")

    def category(self, conditions: list[str], text: str, device_name: str = "") -> tuple[str, dict | None]:
        low = (text or "").lower()
        for r in self.rules:
            if not (r["condition"] or r["text"]):
                continue
            if r["device"] and not _glob_any(r["device"], [device_name]):
                continue
            if (r["condition"] and _glob_any(r["condition"], conditions)) or (r["text"] and r["text"].search(low)):
                return r["category"], r
        return "other", None

    def shows_other(self, severity: str) -> bool:
        floor = str(self.display.get("other_min_severity", "critical")).lower()
        if floor == "none":
            return False
        return SEV_RANK.get(severity, 9) <= SEV_RANK.get(floor, 0)
