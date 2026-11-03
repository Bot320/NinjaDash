# NinjaDash: plan

A calm, good-looking wall dashboard for NinjaOne. An old MSI mini PC drives a 1080p TV in
kiosk mode. It pulls data from the NinjaOne API (EU) and answers three questions from
across the room:

1. **Is any hardware failing?** (disks, RAID, power supplies, memory)
2. **Did backups fail, or is there an antivirus threat?**
3. **Which servers are affected?** Servers come first. Workstations are shown too, with lower priority.

![Dark preview](preview/dashboard-dark.png)

Light theme: [`preview/dashboard-light.png`](preview/dashboard-light.png). The live mockup is
[`mockup/index.html`](mockup/index.html); open it in a browser, and add `?theme=light` for the
light theme. All names and numbers in it are made up.

---

## 1. Design goals

| Goal | What it means in practice |
|---|---|
| **Glanceable from 3 m** | The three focus areas sit across the top, each with one big number and a status chip. You can tell whether something is wrong in under 2 s. |
| **Servers first** | Servers get the largest panel. Servers with problems are shown as big cards at the top of it, sorted worst first. Healthy servers shrink to small green tiles below. |
| **Calm by default** | When everything is fine, the screen is mostly neutral with small green dots. Red and amber only appear where something is actually wrong, and always with an icon and a word. |
| **One screen, no interaction** | No scrolling or clicking. It's a wall display. |
| **Kind to old hardware** | Plain HTML/CSS/SVG with no frontend framework or build step. Redraws only when data changes. |

## 2. Layout (1920 × 1080, 12-column grid)

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ ▣ Infrastructure health                       ● NinjaOne synced 18 s ago 14:32 │
├──────────────────┬──────────────────┬──────────────────┬──────────────────────┤
│ ▤ Hardware  ● Crit│ ↻ Backups  ● Crit│ ⛉ Antivirus ● Crit│ Online now          │
│ 6 devices         │ 3 devices        │ 3 devices         │ Servers      45/46  │
│ [3 servers] 3 ws  │ [2 servers] 1 ws │ [1 server] 2 ws   │ Workstations 356/392│
├───────────────────┴──────────────────┴──┬───────────────┴──────────────────────┤
│ Servers           6 need attention      │ Workstations needing attention       │
│ ┃SRV-FS01  RAID degraded  ● Critical    │ severity + category icon, device,    │
│ ┃SRV-RDS02 Active threat  ● Critical    │ organisation, how long               │
│ ┃SRV-SQL01 Backup failed, SMART  ...    │ (worst first, max ~6)                │
│ ┃SRV-PRINT Offline · HV-HOST02 PSU ...  ├──────────────────────────────────────┤
│ ── Healthy · 40 servers ─────────────── │ New incidents · last 14 days         │
│ ● SRV-DC01  ● SRV-DC02  ● SRV-APP01 ... │ Hardware  ▁ ▂ ▁ ▃ ▁  ▅   17          │
│ (small tiles, grouped by organisation)  │ Backup    ▁   ▂   ▁  ▂    8          │
│                                         │ Antivirus   ▁      ▁ ▃    5          │
└─────────────────────────────────────────┴──────────────────────────────────────┘
```

| Panel | Question it answers | What it shows |
|---|---|---|
| **Hardware failures** | Is hardware breaking? | Devices with an open hardware problem, split into servers (outlined) and workstations, plus the worst status |
| **Backups** | Did backups run? | Devices with a failed or missing backup, and the job success rate over 24 h |
| **Antivirus threats** | Is anything infected or unprotected? | Devices with an active or quarantined threat, or with antivirus disabled or out of date |
| Online now | Is everything reachable? | Servers and workstations online, as two meters |
| **Servers** | Which servers do I fix first? | A big card per affected server, with every issue on that server, its age and a status chip. Offline servers count as affected. Then all healthy servers as small tiles |
| Workstations needing attention | Which client PCs have a problem? | The worst ~6 workstation issues, with category and severity |
| New incidents · 14 days | Is this normal or getting worse? | Three small column charts (hardware / backup / antivirus), today highlighted |

**Scaling:** the mockup has 46 servers. At around 70 servers the healthy tiles switch to name-only
chips. Past around 120, healthy servers collapse into one line per organisation ("Acme Logistics · 10 healthy").
Affected servers are always shown in full.

### Severity rules (first draft)

| Severity | Examples |
|---|---|
| **Critical** | RAID degraded or failed, SMART says the disk is failing, an active (unresolved) threat, antivirus disabled, a server offline > 15 min, backup failed 2× in a row or no good backup for > 48 h |
| **Warning** | Lost PSU or fan redundancy, rising SMART counters, memory (WHEA) errors, a quarantined threat in the last 24 h, a single failed backup, outdated antivirus definitions |
| **Minor** | Laptop battery health < 50 %, other early-warning signals |

### Visual system

- **Font:** Inter, self-hosted so it works offline.
- **Status colours, used for nothing else:** critical `#d03b3b`, warning `#fab219`, OK `#0ca30c`, offline grey. They always come with an icon and a word.
- **Category icons:** a drive (hardware), a circular arrow (backup), a shield (antivirus). They are drawn in neutral ink, so colour only ever means severity.
- **Themes:** light and dark switch automatically (`THEME=auto`: light 07:00–19:00). `THEME=dark` / `light` pins one.
- **Screen:** 1080p TV, not OLED, so no burn-in measures are needed. Set the TV's picture size to *Just Scan* / *Screen Fit* / *PC mode*, or overscan crops the edges.

## 3. Where the data comes from (all to verify in phase 1)

| Need | NinjaOne API v2 | Notes |
|---|---|---|
| Server or workstation? | `GET /devices-detailed` → `nodeClass` | `WINDOWS_SERVER`, `LINUX_SERVER`, `VMWARE_VM_HOST`, `HYPERV_VMM_HOST`, … are servers. `WINDOWS_WORKSTATION`, `MAC`, `LINUX_WORKSTATION` are workstations |
| Online / offline | `GET /devices-detailed` → `offline`, `lastContact` | |
| **Hardware** | `GET /alerts` (hardware conditions), `GET /queries/raid-controllers`, `GET /queries/raid-drives`, `GET /queries/disks` | SMART, RAID and PSU problems usually arrive as **alerts from monitoring conditions** in your NinjaOne policies, for example disk health, RAID health, or Windows event IDs 7/51/153 (disk) and WHEA 17–19 (memory/CPU). The backend sorts alerts into hardware/backup/antivirus by condition type and keywords; the mapping lives in one config file |
| **Backup** | `GET /backup/jobs` if you use NinjaOne's own backup, otherwise backup alerts | Auto-detected, see §6 |
| **Antivirus** | `GET /queries/antivirus-status`, `GET /queries/antivirus-threats` | Works for Microsoft Defender and the antivirus products NinjaOne integrates with |
| Organisation names | `GET /organizations` | |
| 14-day trend | our own SQLite history | NinjaOne only returns the current state, so the backend stores daily counts itself |

### Custom alerts (Veeam, NAS, anything else)

The dashboard shows **every active alert NinjaOne raises**, including alerts from conditions you
built yourself. The one rule: NinjaOne has to raise the alert. If no condition watches for a problem,
neither NinjaOne nor the dashboard can see it.

| Example | How NinjaOne sees it | Dashboard category |
|---|---|---|
| Veeam backup job failed | *Windows Event Log* condition on the Veeam server: source **Veeam MP** / log **Veeam Backup**, job-finished events whose text contains "Failed" or "Warning" (event IDs to confirm on your Veeam version), or a script condition that checks the last job result | Backup |
| NAS drive or RAID failed (Synology, QNAP, …) | The NAS has no agent, so it's monitored through **NinjaOne network monitoring (SNMP)**, with an agent PC on the same LAN acting as the probe. SNMP conditions on the NAS's disk and RAID status values raise the alert | Hardware, on a server card |
| Anything else (UPS on battery, temperature, a service down) | Any condition or script that raises an alert | Mapped by rule, or shown as "Other" |

Sorting alerts into categories uses an editable rule file (`/etc/ninjadash/classify.toml`, on top of the built-in `backend/classify.toml`), for example:

```toml
[[rule]]
condition = ["Veeam*"]                      # condition name you gave it in NinjaOne
category  = "backup"

[[rule]]
text      = ["raid", "drive failed", "s.m.a.r.t"]
category  = "hardware"

[tiers]
server_classes = ["*SERVER*", "*_HOST", "NMS*"]   # SNMP devices (NAS, switches) count as servers
server_names   = ["NAS-*", "FW-*"]
```

Alerts that match no rule still show up, under "Other", so nothing gets lost. A device's NinjaOne
**name** can also pin the tier (`server_names`), so a NAS or firewall appears with the servers.

## 4. Architecture

```
NinjaOne API  eu.ninjarmm.com  (OAuth2 client-credentials, read-only "monitoring" scope)
        │  HTTPS, polled
        ▼
┌──────────────── MSI mini PC · CachyOS · 4 GB RAM ───────────────┐
│  ninjadash.service (Python 3, standard library only)            │
│   ├─ reads secrets from /etc/ninjadash/ninjadash.env            │
│   ├─ poller: alerts + devices every 60 s, AV/RAID/backup 5 min  │
│   ├─ classifier: alert → hardware | backup | antivirus, sev     │
│   ├─ SQLite: daily incident counts → 14-day trend               │
│   └─ GET /api/summary  (one JSON blob, same shape as mockup)    │
│        │ http://127.0.0.1:8080                                  │
│        ▼                                                        │
│  cage (Wayland kiosk) → Chromium --kiosk  (tty1 autologin)      │
└─────────────────────────────────────────────────────────────────┘
        │ HDMI
        ▼
      1080p TV
```

- **Secrets stay on the mini PC.** The client secret lives in one root-owned file outside the repo and never reaches the browser.
- **One poller.** This stays well under API rate limits, even if a laptop also opens the page.
- **Fits in 4 GB on CachyOS.** No desktop session: tty1 autologin starts `cage` + Chromium directly (around 400–600 MB). If a desktop like KDE is installed, its display manager is disabled. Packages come from pacman (`cage`, `chromium`, `python`), and the backend runs in its own venv. Firefox kiosk is the fallback.

## 5. Phases

| # | Phase | Output | Status |
|---|---|---|---|
| 0 | **Plan + design** | Folders, this plan, mockup, demo, preview images | Done |
| 1 | **API check** | `ninjadash check` logs in and shows which §3 sources have data in your account, plus alerts no rule sorts yet | Built; waiting for the API client from the NinjaOne admin |
| 2 | **Backend** | Token handling, poller, alert classifier, server/workstation split, SQLite trend, `/api/summary`, `/healthz` | Built; tested against a fake NinjaOne API |
| 3 | **Frontend** | Live data every 30 s, stale-data warning, example data until configured, automatic light/dark | Built |
| 4 | **Kiosk** | `deploy/install.sh` for CachyOS, systemd services, cage + Chromium on tty1 | Installed on the mini PC (2026-11-03) with Home Assistant switch and RDP (XFCE) |
| 5 | **Polish** (optional) | Screen off outside office hours, weekly reboot, a per-organisation page that rotates in | Later (new critical servers already flash) |

## 6. Decisions

| Question | Answer | Effect on the build |
|---|---|---|
| NinjaOne region | **EU** | `NINJA_HOST=eu.ninjarmm.com` |
| Screen | **1080p TV, not OLED** | Fixed 1920 × 1080 layout, no burn-in measures |
| Ticketing | **Not used** | No ticket panel or calls |
| Focus | **Hardware, backup and antivirus; servers first** | Layout above (2026-11-03) |
| Backup source | *Unknown* | Phase 1 checks: if `GET /backup/jobs` returns jobs, NinjaOne's own backup is used. Otherwise backup failures come from alerts (for example Veeam or Windows Server Backup event-log conditions). If neither exists, the Backups tile says "No backup monitoring found" instead of a false green |
| Mini PC | **4 GB RAM, CachyOS** | No desktop session, cage + Chromium on tty1, pacman packages, backend in a venv |
| Theme | **Light and dark** | `THEME=auto`, light 07:00–19:00 |
| Boot | **Straight into the dashboard, no login manager** | Installer disables SDDM; `ninjadash desktop` / `kiosk` swap the TV between KDE and the dashboard |
| Screen off | **From Home Assistant** | `/api/screen` with a token; a screen agent cuts HDMI via `wlr-randr` (cage 0.3 supports output management); only the switch is reachable from the network |
| Remote maintenance | **RDP** | xrdp (AUR) with an XFCE session, because Plasma 6.8 has no X11 session; the TV keeps showing the dashboard |
