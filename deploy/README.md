# deploy

Kiosk setup for the MSI mini PC (CachyOS, 4 GB RAM, 1080p TV over HDMI).

- Packages: `sudo pacman -S --needed cage chromium python`
- `systemd/ninjadash.service`: runs the backend from a venv in `/opt/ninjadash` as the unprivileged `ninjadash` user
- tty1 autologin (`getty@tty1` drop-in) for a `kiosk` user, whose login shell starts `cage -- chromium --kiosk http://127.0.0.1:8080`
- If a desktop is installed, `systemctl disable sddm` (or the active display manager) so it doesn't hold RAM
- `kiosk/`: launcher script, Chromium flags (no first-run, no translate bar, no crash bubble, low memory), screen-off schedule
- `install.sh` (later): one-shot setup script

TV: set the picture size to *Just Scan* / *Screen Fit* / *PC mode*, or the edges get cropped.
