# NinjaDash: plan

A calm, good-looking wall dashboard for NinjaOne. An old MSI mini PC drives a TV or monitor
in kiosk mode. It pulls data from the NinjaOne public API and shows the whole fleet on one
screen that you can read from across the room.

![Dark preview](preview/dashboard-dark.png)

Light theme: [`preview/dashboard-light.png`](preview/dashboard-light.png). The live mockup is in
[`mockup/index.html`](mockup/index.html). It's a single file you can open in a browser
(add `?theme=light` to the URL for the light theme). All data in it is made up.

---

## 1. Design goals

| Goal | What it means in practice |
|---|---|
| **Glanceable from 3 m** | One hero number, big KPI values, nothing smaller than 12 px. You can tell whether something is wrong in under 2 s. |
| **Calm by default** | Dark, low-contrast surfaces. Colour is used only where it means something: status (critical / major / minor / OK). Everything else is neutral ink plus one blue accent. |
| **Informational, not decorative** | Every panel answers a question an admin actually asks (see §2). No 3D, no gauges, no pie charts. |
| **One screen, no interaction** | No scrolling and no clicking needed. It's a wall display, so hover is a bonus, not a requirement. |
| **Kind to old hardware** | Plain HTML/CSS/SVG with no frontend framework or build step. Redraws only when data changes. |

## 2. Layout (1920 × 1080, 12-column grid, 20 px gaps)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ ▣ Fleet overview                            ● NinjaOne synced 18 s ago   14:32 │
│   6 organisations · 438 devices                                Monday, 2 Nov   │
├────────────┬────────────┬────────────┬────────────┬────────────┬────────────┤
│ Devices    │ Active     │ Patch      │ Backups    │ Pending    │ Antivirus  │
│ online     │ alerts     │ compliance │ last 24 h  │ reboots    │ protected  │
│ 401/438 ⌇  │ 23         │ 93.9 % ▬▬  │ 97.8 %     │ 17         │ 431/438    │
├────────────┴────────────┴───────┬────┴────────────┬───────────┴────────────┤
│ Alerts triggered · last 24 h    │ Device inventory │ Latest alerts          │
│ stacked columns per hour,       │ segmented bar by │ live feed, newest      │
│ by severity                     │ OS + list        │ first, icon + severity │
├─────────────────────┬───────────┴──────────────────┤ word + device + org    │
│ Patch compliance    │ Needs attention              │ + time ago             │
│ by organisation     │ devices with a problem state │                        │
│ (90 % target mark)  │ (offline, disk, backup, …)   │                        │
└─────────────────────┴──────────────────────────────┴────────────────────────┘
```

| Panel | Question it answers | Form | NinjaOne source (to verify in phase 1) |
|---|---|---|---|
| Header sync pill | Is the data fresh? | Green dot, turns amber after 5 min and red after 15 | backend's own last sync time |
| **Devices online** (hero) | Is the fleet up? | Hero number + 14-day sparkline | `GET /v2/devices` → `offline` flag; trend from our own history DB |
| Active alerts | How bad is it right now? | Number + severity breakdown | `GET /v2/alerts` → `severity` |
| Patch compliance | Are we patched? | % + meter + pending / failed | `GET /v2/queries/os-patches`, `/v2/queries/os-patch-installs` |
| Backups · 24 h | Did last night's backups run? | % + ok/total + delta | `GET /v2/backup/jobs`. If the account has no NinjaOne Backup jobs, this tile becomes **Low disk space** (volumes > 90 % full, from `GET /v2/queries/volumes`) |
| Pending reboots | What is waiting on a restart? | Count + overdue count | device health / pending-reboot fields |
| Antivirus | Is everything protected? | protected / total + threats | `GET /v2/queries/antivirus-status`, `/v2/queries/antivirus-threats` |
| Alerts · 24 h | Is today normal? | Stacked columns, critical on the baseline | alerts + our own history (the API has no alert history) |
| Device inventory | What do we manage? | Segmented bar + list with online counts | `GET /v2/devices` → `nodeClass` |
| Latest alerts | What just happened? | Feed with icon + severity word | `GET /v2/alerts` sorted by `createTime` |
| Patch by org | Which customer is behind? | Bars with a 90 % target mark; below target turns amber with a ⚠ | patch queries grouped by `organizationId` |
| Needs attention | Which devices do I fix first? | Table with a status pill and how long | offline > 30 min, disk > 90 %, backup failed, reboot > 7 d, encryption off |

### Visual system

- **Font:** Inter (self-hosted on the mini PC so it works offline), tabular figures only in columns and axes.
- **Surfaces:** page `#0b0c0e`, cards `#16181c`, 18 px radius, hairline borders.
- **Themes:** light and dark switch automatically (`THEME=auto`: light 07:00–19:00, dark otherwise; times configurable). `THEME=dark` / `light` pins one.
- **Screen:** 1080p TV, not OLED, so a static layout is fine and no burn-in protection is needed. Set the TV's picture size to *Just Scan* / *Screen Fit* / *PC mode*. Otherwise overscan crops the edges.
- **Status colours, used for nothing else:** critical `#d03b3b`, major `#ec835a`, minor/warning `#fab219`, good `#0ca30c`. They always appear with an icon or a word, never colour alone.
- **Category colours (device types):** blue, orange, aqua, yellow, magenta, in that fixed order. Checked for colour-blind separation in both themes.
- **Charts:** thin bars (≤ 22 px), a 4 px rounded top, a 2 px gap between stacked parts, hairline grid, and a label only on the peak.

## 3. Architecture

```
NinjaOne cloud API  eu.ninjarmm.com  (OAuth2 client-credentials, read-only "monitoring" scope)
        │  HTTPS, polled
        ▼
┌──────────────── MSI mini PC · CachyOS · 4 GB RAM ───────────────┐
│  ninjadash-backend (Python 3 · FastAPI · httpx, systemd)        │
│   ├─ poller: alerts/devices every 60 s, patches/AV/backups 10 m │
│   ├─ SQLite: hourly snapshots → sparklines, "vs yesterday"      │
│   └─ GET /api/summary  (one JSON blob, same shape as mockup)    │
│        │ http://127.0.0.1:8080                                  │
│        ▼                                                        │
│  cage (Wayland kiosk) → Chromium --kiosk  (autologin on tty1)   │
└─────────────────────────────────────────────────────────────────┘
        │ HDMI
        ▼
      TV / monitor
```

Why this stack:
- **Secrets stay server-side.** The NinjaOne client secret never reaches the browser.
- **One poller, not one per browser.** This keeps us well under API rate limits, even if a second screen or a laptop also opens the page.
- **History is ours.** NinjaOne's API returns current state. Sparklines and "vs yesterday" need our own small snapshot DB.
- **Fits in 4 GB on CachyOS.** No desktop session: autologin on tty1 starts `cage` + Chromium directly, which idles at around 400–600 MB for one static page. If a desktop (KDE/SDDM) was installed, the display manager gets disabled so it doesn't hold RAM. The backend is about 60 MB. Everything comes from the normal Arch/CachyOS repos (`cage`, `chromium`, `python`), and the backend runs in its own venv so pacman's Python stays untouched. Firefox kiosk is the fallback if Chromium is too heavy.

## 4. Phases

| # | Phase | Output |
|---|---|---|
| 0 | **Plan + design** (this PR) | Folders, this plan, mockup, preview images |
| 1 | **API spike** | Create a NinjaOne API client (machine-to-machine, `monitoring` scope). Write a script that dumps real responses to `cache/samples/`. Confirm every field in the §2 table. |
| 2 | **Backend** | Token handling + refresh, poller, SQLite history, `/api/summary`, `/healthz`, retries with backoff |
| 3 | **Frontend** | Turn the mockup into `frontend/` and fetch `/api/summary` every 30 s. Add stale-data banner, empty and error states, auto light/dark by time of day |
| 4 | **Kiosk** | Install script for CachyOS (`pacman -S cage chromium python`), `ninjadash` system user + venv, systemd units, tty1 autologin into cage, screen off outside office hours (`wlr-randr` / HDMI-CEC), auto-reboot weekly |
| 5 | **Polish** (optional) | A second rotating page (per-organisation detail) and a flash on a new critical alert |

## 5. Folder layout

```
backend/        Python service: NinjaOne client, poller, history DB, JSON API
frontend/       Static dashboard page (HTML/CSS/vanilla JS), fonts in assets/
deploy/         Kiosk setup: systemd units, cage/Chromium launcher, install script
config/         .env.example (real .env is gitignored)
docs/           This plan, mockup, preview images
```

## 6. Decisions (2026-11-03)

| Question | Answer | Effect on the build |
|---|---|---|
| NinjaOne region | **EU** | `NINJA_HOST=eu.ninjarmm.com`; the token URL is `https://eu.ninjarmm.com/ws/oauth/token` |
| Screen | **1080p TV, not OLED** | Layout stays exactly 1920 × 1080. No burn-in measures |
| Ticketing | **Not used** | No ticket panel or API calls |
| Backup | *Not answered yet* | Auto-detected: no NinjaOne Backup jobs → the tile shows **Low disk space** instead |
| Mini PC | **4 GB RAM, CachyOS** | No desktop session, cage + Chromium on tty1, pacman packages, backend in a venv |
| Theme | **Light and dark** | `THEME=auto`, light 07:00–19:00 |
