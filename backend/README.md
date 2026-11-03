# backend

Python 3.11+, standard library only (no pip installs). Run with `PYTHONPATH=backend python3 -m ninjadash`.

| Module | Does |
|---|---|
| `ninjadash/config.py` | Loads settings from `$NINJADASH_ENV`, `/etc/ninjadash/ninjadash.env` or `~/.config/ninjadash/ninjadash.env`; real environment variables override |
| `ninjadash/ninja.py` | NinjaOne API v2 client: OAuth2 client credentials, retries on 429/5xx, paging |
| `ninjadash/classify.py` | Server / workstation tier, alert category and severity, from `classify.toml` |
| `ninjadash/summary.py` | Builds `/api/summary` from devices, alerts, antivirus and backup data |
| `ninjadash/history.py` | SQLite "first seen" log for the 14-day trend |
| `ninjadash/app.py` | Poller thread; falls back to example data without credentials |
| `ninjadash/server.py` | Serves the frontend, `/api/summary` and `/healthz` |
| `ninjadash/__main__.py` | `serve` (default) and `check` commands |
| `classify.toml` | Built-in rules. Local additions go in `/etc/ninjadash/classify.toml` |

Field names for the antivirus, backup and alert endpoints are read defensively (several known
spellings). `ninjadash check --fields` prints what a real account returns, so the parser can be adjusted.
