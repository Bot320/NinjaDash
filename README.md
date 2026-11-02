# NinjaDash

A calm, good-looking wall dashboard for **NinjaOne RMM**. It runs on a small (old) MSI mini PC
in kiosk mode and shows the whole fleet on one screen: device health, alerts, patching,
backups, antivirus and what needs attention.

![Preview](docs/preview/dashboard-dark.png)

> Status: **planning**. See [docs/PLAN.md](docs/PLAN.md) for the design, architecture and phases.
> The preview uses made-up example data.

## Layout

| Folder | Contents |
|---|---|
| `backend/` | Python service: NinjaOne API client, poller, history DB, `/api/summary` |
| `frontend/` | The dashboard page (plain HTML/CSS/JS, no build step) |
| `deploy/` | Kiosk setup for the mini PC (systemd, cage + Chromium) |
| `config/` | `.env.example`; copy it to `.env` and fill in your API client |
| `docs/` | Plan, clickable mockup (`docs/mockup/index.html`), preview images |
