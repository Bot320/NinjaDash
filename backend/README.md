# backend

Python 3 · FastAPI · httpx. Planned modules in `app/`:

- `ninja.py`: OAuth2 client-credentials token + typed calls to the NinjaOne v2 API
- `poller.py`: fast loop (alerts, device state) and slow loop (patches, AV, backups)
- `history.py`: SQLite hourly snapshots for sparklines and "vs yesterday"
- `summary.py`: builds the single `/api/summary` JSON (same shape as `DATA` in `docs/mockup/index.html`)
- `main.py`: FastAPI app, serves `../frontend` statically, plus `/api/summary` and `/healthz`
