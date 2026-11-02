# deploy

Kiosk setup for the MSI mini PC (Debian 13 minimal, no desktop).

- `systemd/ninjadash.service`: runs the backend as an unprivileged `ninjadash` user
- `systemd/kiosk.service` or autologin on tty1: starts `cage -- chromium --kiosk http://127.0.0.1:8080`
- `kiosk/`: launcher script, Chromium flags (no first-run, no translate bar, no crash bubble), screen-off schedule
- `install.sh` (later): one-shot setup script
