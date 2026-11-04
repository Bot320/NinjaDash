"""Command line: `python -m ninjadash serve` (default) or `python -m ninjadash check`."""
from __future__ import annotations

import argparse
import collections
import logging
import sys
import time

from . import __version__
from .classify import Classifier
from .config import load_config
from .ninja import NinjaClient, NinjaError
from .summary import patch_reason, patch_state, Snapshot, build_summary, device_name, first


def cmd_serve(args) -> int:
    from .app import App
    from .server import serve
    cfg = load_config()
    if args.demo:
        cfg.demo = True
    if args.port:
        cfg.listen_port = args.port
    logging.info("NinjaDash %s · settings: %s · rules: %s", __version__, cfg.env_file or "(none found)", cfg.rules_file)
    app = App(cfg)
    app.start()
    serve(app, cfg.listen_host, cfg.listen_port, cfg.frontend_dir)
    return 0


_TTY = sys.stdout.isatty()
def _ok(msg):   print(f"  {'\033[32m✓\033[0m' if _TTY else '✓'} {msg}")
def _bad(msg):  print(f"  {'\033[31m✗\033[0m' if _TTY else '✗'} {msg}")
def _info(msg): print(f"    {msg}")


SHOWN = {"approval": "awaiting approval", "queued": "approved, not installed", "failed": "failed",
         None: "not shown"}


def cmd_patches(args) -> int:
    """Compact look at the raw patch data, small enough for one photo. Read-only, no device names."""
    cfg = load_config()
    if not cfg.has_credentials:
        _bad("NINJA_CLIENT_ID / NINJA_CLIENT_SECRET are empty.")
        return 2
    c = NinjaClient(cfg.api_base, cfg.client_id, cfg.client_secret, cfg.scope)
    now = time.time()
    print(f"NinjaDash {__version__} · patch data as NinjaOne sends it (nothing is changed)")
    for label, fn in (("OS patches", lambda: c.os_patches(attempts=2)),
                      ("App updates", lambda: c.query("/v2/queries/software-patches", attempts=2))):
        print(f"\n{label}")
        try:
            rows = fn()
        except NinjaError as e:
            _bad(f"not available: {e}")
            continue
        _info(f"{len(rows)} records")
        if not rows:
            continue
        keys = sorted({k for r in rows for k in r})
        _info("fields: " + ", ".join(keys))
        by_status: dict = collections.defaultdict(list)
        for r in rows:
            by_status[str(first(r, "status", "patchStatus", "approvalStatus", "state", default="?"))].append(r)
        for status, rs in sorted(by_status.items(), key=lambda kv: -len(kv[1])):
            devs = {first(r, "deviceId", "nodeId") for r in rs}
            states = collections.Counter(SHOWN[patch_state(r, now)] for r in rs)
            _info(f"status {status}: {len(rs)} on {len(devs)} devices → " + ", ".join(f"{n} {w}" for w, n in states.most_common()))
            why = collections.Counter(patch_reason(r, now) for r in rs)
            _info("  because: " + "; ".join(f"{w} ({n})" for w, n in why.most_common(3)))
            ex = {k: v for k, v in rs[0].items() if k not in ("deviceId", "nodeId")}
            _info("  e.g. " + "  ".join(f"{k}={str(v)[:38]}" for k, v in ex.items())[:400])
    print("\nTake a photo of this screen and send it.")
    return 0


def cmd_check(args) -> int:
    """Talks to NinjaOne and reports what the dashboard would see. Read-only."""
    cfg = load_config()
    print(f"NinjaDash {__version__} check")
    print(f"  Settings file: {cfg.env_file or 'none found'}")
    print(f"  Rules file:    {cfg.rules_file}")
    print(f"  API:           {cfg.api_base}")
    if not cfg.has_credentials:
        _bad("NINJA_CLIENT_ID / NINJA_CLIENT_SECRET are empty. Fill them in the settings file first.")
        return 2
    c = NinjaClient(cfg.api_base, cfg.client_id, cfg.client_secret, cfg.scope)
    clf = Classifier(cfg.rules)
    snap = Snapshot()
    print("\nConnection")
    try:
        c._fetch_token()
        _ok("Logged in to NinjaOne")
    except NinjaError as e:
        _bad(str(e))
        return 1

    print("\nRequired data")
    try:
        snap.orgs = c.organizations()
        _ok(f"Organizations: {len(snap.orgs)}")
        snap.devices = c.devices()
        _ok(f"Devices: {len(snap.devices)}")
        snap.alerts = c.alerts()
        _ok(f"Active alerts: {len(snap.alerts)}")
    except NinjaError as e:
        _bad(str(e))
        return 1

    classes = collections.Counter(str(d.get("nodeClass")) for d in snap.devices)
    tiers = collections.Counter(clf.tier(str(d.get("nodeClass", "")), device_name(d)) or "ignored" for d in snap.devices)
    print("\nDevices by type (nodeClass → tier)")
    for cls, n in classes.most_common():
        _info(f"{n:5}  {cls:28} → {clf.tier(cls, '') or 'ignored'}")
    _info(f"Total: {tiers['server']} servers, {tiers['workstation']} workstations, {tiers['ignored']} ignored")

    print("\nOptional data")
    for label, attr, fn in (
        ("Antivirus status", "av_status", lambda: c.query("/v2/queries/antivirus-status", attempts=2)),
        ("Antivirus threats", "av_threats", lambda: c.query("/v2/queries/antivirus-threats", attempts=2)),
        ("NinjaOne Backup jobs", "backup_jobs", lambda: c.backup_jobs(attempts=2)),
        ("OS patches", "os_patches", lambda: c.os_patches(attempts=2)),
        ("App (software) patches", "sw_patches", lambda: c.query("/v2/queries/software-patches", attempts=2)),
        ("Disk volumes", "volumes", lambda: c.query("/v2/queries/volumes", attempts=2)),
    ):
        try:
            rows = fn()
            setattr(snap, attr, rows)
            _ok(f"{label}: {len(rows)} records")
            if rows and args.fields:
                _info("fields: " + ", ".join(sorted(rows[0].keys())))
            if rows and attr in ("os_patches", "sw_patches"):
                def st(r):
                    return str(first(r, "status", "patchStatus", "approvalStatus", "state", default="?"))
                statuses = collections.Counter(st(r) for r in rows)
                devs_per = collections.defaultdict(set)
                where = collections.defaultdict(collections.Counter)
                now = time.time()
                for r in rows:
                    devs_per[st(r)].add(first(r, "deviceId", "nodeId"))
                    where[st(r)][SHOWN[patch_state(r, now)]] += 1
                for k, v in statuses.most_common(8):
                    _info(f"status {k}: {v} patches on {len(devs_per[k])} devices → "
                          + ", ".join(f"{n} {w}" if len(where[k]) > 1 else w for w, n in where[k].most_common()))
        except NinjaError as e:
            _bad(f"{label}: not available, that part stays empty (the rest works). {e}")

    print("\nAlerts by category (what the three tiles will count)")
    devs = {d.get("id"): d for d in snap.devices}
    cats, sevs, other = collections.Counter(), collections.Counter(), collections.Counter()
    for a in snap.alerts:
        subject = first(a, "subject", default="") or ""
        message = first(a, "message", default="") or ""
        src = a.get("sourceConfig") if isinstance(a.get("sourceConfig"), dict) else {}
        conds = [str(x) for x in (a.get("sourceName"), a.get("conditionName"), a.get("sourceConfigName"), src.get("name"), subject) if x]
        d = devs.get(first(a, "deviceId", "nodeId")) or {}
        cat, rule = clf.category(conds, f"{subject} {message} {' '.join(conds)}", device_name(d) if d else "")
        cats[cat] += 1
        sevs[str(a.get("severity") or a.get("priority"))] += 1
        if cat == "other":
            other[(conds[0] if conds else str(message).splitlines()[0] if message else "?")[:70]] += 1
    for cat in ("hardware", "backup", "antivirus", "other"):
        _info(f"{cats[cat]:5}  {cat}")
    _info("NinjaOne severities: " + ", ".join(f"{k} {v}" for k, v in sevs.most_common()))
    if other:
        print("\nMost common alerts that match no rule (add rules for the ones that matter)")
        for text, n in other.most_common(15):
            _info(f"{n:5}  {text}")
    if snap.alerts and args.fields:
        print("\nAlert fields (first alert): " + ", ".join(sorted(snap.alerts[0].keys())))

    s = build_summary(snap, clf, None, time.time())
    print("\nDashboard preview")
    for cat in ("hardware", "backup", "antivirus"):
        p = s["pillars"][cat]
        _info(f"{cat:10} {p['servers']} server(s), {p['workstations']} workstation(s) · {p['state']} · {p['note']}")
    _info(f"Servers needing attention: {len(s['affected'])} · healthy: {len(s['healthy'])}")
    for srv in s["affected"][:10]:
        _info(f"  {srv['name']} ({srv['org']}): " + "; ".join(i["text"] for i in srv["issues"]))
    _info(f"Workstation issues: {s['workstationTotal']}")
    for key, label in (("os", "OS patches"), ("apps", "App updates")):
        u = s["updates"][key]
        if u:
            _info(f"{label}: {u['approval']} awaiting approval on {u['approvalDevices']} devices "
                  f"({u['autoApprove']} approve automatically later), {u['queued']} approved, {u['failed']} failed")
            for t in u["top"][:8]:
                _info(f"  {t['name'][:60]}: {t['devices']} waiting, {t['approved']} approved")
    st = s["updates"]["storage"]
    if st:
        _info(f"Low storage: {st['total']} volumes ≥ {st['warnPercent']:.0f} % full ({st['critical']} critical)")
    print("\nDone. Nothing was changed in NinjaOne (read-only access).")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ninjadash", description="NinjaOne wall dashboard")
    parser.add_argument("--version", action="version", version=f"ninjadash {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    p_serve = sub.add_parser("serve", help="run the dashboard (default)")
    p_serve.add_argument("--demo", action="store_true", help="show example data")
    p_serve.add_argument("--port", type=int, help="override the port from LISTEN")
    p_check = sub.add_parser("check", help="test the NinjaOne connection and show what the dashboard would see")
    p_check.add_argument("--fields", action="store_true", help="also print the field names NinjaOne returns")
    sub.add_parser("patches", help="show the raw patch statuses and fields NinjaOne sends (for one photo)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "patches":
        return cmd_patches(args)
    if args.cmd is None:
        args.demo, args.port = False, None
    return cmd_serve(args)


if __name__ == "__main__":
    sys.exit(main())
