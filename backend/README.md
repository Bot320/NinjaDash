# backend

Python 3 · FastAPI · httpx. Planned modules in `app/`:

- `config.py`: loads settings from `$NINJADASH_ENV`, `/etc/ninjadash/ninjadash.env` or `~/.config/ninjadash/ninjadash.env`, never from the repo
- `ninja.py`: OAuth2 client-credentials token + calls to the NinjaOne v2 API (EU)
- `poller.py`: fast loop (alerts, online state) and slow loop (antivirus, RAID, backup)
- `classify.py`: maps each alert to hardware / backup / antivirus and to critical / warning / minor (rules in `classify.yaml`)
- `history.py`: SQLite daily incident counts for the 14-day trend
- `summary.py`: builds `/api/summary` (same shape as `DATA` in `docs/mockup/index.html`), servers first
- `main.py`: FastAPI app, serves `../frontend` statically, plus `/api/summary` and `/healthz`
