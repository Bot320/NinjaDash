#!/usr/bin/env bash
# Removes NinjaDash. Keeps your settings (/etc/ninjadash) and history (/var/lib/ninjadash)
# unless you pass --purge. Re-enables the desktop login screen if the installer disabled it.
set -euo pipefail
PURGE=0
[[ ${1:-} == --purge ]] && PURGE=1
[[ $EUID -eq 0 ]] || exec sudo -- bash "$0" "$@"

systemctl disable --now ninjadash-kiosk.service ninjadash.service 2>/dev/null || true
rm -f /etc/systemd/system/ninjadash.service /etc/systemd/system/ninjadash-kiosk.service \
      /etc/pam.d/ninjadash-kiosk /usr/local/bin/ninjadash
systemctl daemon-reload
rm -rf /opt/ninjadash
for home in /home/*; do rm -f "$home/.config/autostart/ninjadash.desktop"; done

if [[ -f /etc/ninjadash/.disabled-display-manager ]]; then
  DM=$(cat /etc/ninjadash/.disabled-display-manager)
  systemctl enable "$DM" && systemctl set-default graphical.target && echo "Re-enabled $DM (desktop login after reboot)."
  rm -f /etc/ninjadash/.disabled-display-manager
fi

if [[ $PURGE == 1 ]]; then
  rm -rf /etc/ninjadash /var/lib/ninjadash /var/lib/ninjadash-kiosk
  userdel ninjadash-kiosk 2>/dev/null || true
  userdel ninjadash 2>/dev/null || true
  echo "NinjaDash removed, including settings and history."
else
  echo "NinjaDash removed. Settings kept in /etc/ninjadash (use --purge to delete them too)."
fi
