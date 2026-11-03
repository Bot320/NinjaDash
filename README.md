# NinjaDash

A calm, good-looking wall dashboard for **NinjaOne RMM**. It runs on a small (old) MSI mini PC
in kiosk mode on a 1080p TV and focuses on three things: **hardware failures**, **failed backups**
and **antivirus threats**. It shows which **servers** are affected first, then workstations.

![Preview](docs/preview/dashboard-dark.png)

## Install on the mini PC (Arch / CachyOS)

```
tar xzf ninjadash-0.1.0.tar.gz && cd ninjadash-0.1.0
sudo ./deploy/install.sh
sudo ninjadash edit      # add the NinjaOne API client ID + secret
sudo ninjadash check     # test the connection
sudo reboot              # the TV now shows the dashboard
```

The full guide, with all options, is in [deploy/README.md](deploy/README.md). Build the
`.tar.gz` with `./deploy/make-bundle.sh`.

## How it works

- `backend/`: a small Python service with **no extra packages**. It logs in to the NinjaOne API
  (read-only "Monitoring" scope), polls alerts and devices every minute and antivirus and backup
  data every 5 minutes. It sorts every alert into hardware / backup / antivirus with the rules in
  `classify.toml`, and serves the page plus `/api/summary`.
- `frontend/`: the dashboard page (plain HTML/CSS/JS, no build step). It switches between light
  and dark by time of day.
- `deploy/`: install script, systemd services, and the cage + Chromium kiosk.
- `config/.env.example`: the settings template. The real file with the secret lives in
  `/etc/ninjadash/ninjadash.env`, never in the repo.
- `docs/`: [plan](docs/PLAN.md), mockup, interactive demo and preview images.

## Develop / test without the mini PC

```
python3 -m unittest discover -s tests                         # tests
python3 tests/fake_ninja.py 9911 &                            # fake NinjaOne API
NINJA_BASE_URL=http://127.0.0.1:9911 NINJA_CLIENT_ID=x NINJA_CLIENT_SECRET=test-secret \
  PYTHONPATH=backend python3 -m ninjadash serve --port 8099   # open http://127.0.0.1:8099
PYTHONPATH=backend python3 -m ninjadash serve --demo          # example data only
```
