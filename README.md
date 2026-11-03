# NinjaDash

A calm, good-looking wall dashboard for **NinjaOne RMM**. It runs on a small (old) MSI mini PC
in kiosk mode on a 1080p TV and focuses on three things: **hardware failures**, **failed backups**
and **antivirus threats**. It shows which **servers** are affected first, then workstations.

![Preview](docs/preview/dashboard-dark.png)

> Status: **planning**. See [docs/PLAN.md](docs/PLAN.md) for the design, architecture and phases.
> The preview uses made-up example data.

## Layout

| Folder | Contents |
|---|---|
| `backend/` | Python service: NinjaOne API client, poller, history DB, `/api/summary` |
| `frontend/` | The dashboard page (plain HTML/CSS/JS, no build step) |
| `deploy/` | Kiosk setup for the mini PC (systemd, cage + Chromium) |
| `config/` | `.env.example`, the template for the settings file. The real file with the API secret lives **outside** the repo (`~/.config/ninjadash/ninjadash.env`, or `/etc/ninjadash/ninjadash.env` on the mini PC) |
| `docs/` | Plan, clickable mockup (`docs/mockup/index.html`), preview images |
