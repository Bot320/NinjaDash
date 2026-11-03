#!/usr/bin/env bash
# NinjaDash installer for Arch Linux / CachyOS.
#
#   sudo ./deploy/install.sh                 full kiosk: dashboard full screen on the TV at boot
#   sudo ./deploy/install.sh --backend-only  only the dashboard service; open http://localhost:8080 yourself
#   sudo ./deploy/install.sh --desktop USER  keep the desktop; open the dashboard full screen when USER logs in
#   add --home-assistant to let Home Assistant switch the screen on/off over the network
#   add --yes to answer "yes" to every question (no prompts)
# Remote Desktop (RDP) for maintenance is a separate step: sudo ./deploy/setup-rdp.sh
#
# Running it again updates NinjaDash and keeps your settings in /etc/ninjadash/.
set -euo pipefail

MODE=kiosk
DESKTOP_USER=""
ASSUME_YES=0
HA=""
PREFIX=/opt/ninjadash
ETC=/etc/ninjadash
ORIG_ARGS=("$@")

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }
ask()  {  # ask "question" -> 0 for yes
  [[ $ASSUME_YES == 1 ]] && return 0
  [[ -t 0 ]] || die "$1 (run with --yes to answer yes without a prompt)"
  local a; read -r -p "  $1 [y/N] " a; [[ $a =~ ^[YyJj] ]]
}
setenv() {  # setenv KEY VALUE: set or add a line in the settings file
  local f=$ETC/ninjadash.env
  if grep -q "^$1=" "$f"; then sed -i "s|^$1=.*|$1=$2|" "$f"; else printf '%s=%s\n' "$1" "$2" >> "$f"; fi
}
open_port() {  # open a TCP port in the firewall, if one is active
  if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow "$1/tcp" >/dev/null && ok "Firewall (ufw): opened port $1"
  elif command -v firewall-cmd >/dev/null && systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --add-port="$1/tcp" >/dev/null && firewall-cmd --reload >/dev/null && ok "Firewall (firewalld): opened port $1"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-only) MODE=backend ;;
    --desktop) MODE=desktop; DESKTOP_USER="${2:-}"; shift || true
               [[ -n $DESKTOP_USER ]] || die "--desktop needs a user name, e.g. --desktop $USER" ;;
    --yes|-y) ASSUME_YES=1 ;;
    --home-assistant|--ha) HA=1 ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown option: $1 (see --help)" ;;
  esac
  shift
done

if [[ $EUID -ne 0 ]]; then
  exec sudo -- bash "$0" "${ORIG_ARGS[@]}"
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f $SRC/backend/ninjadash/__init__.py && -f $SRC/frontend/index.html ]] || die "Run this from the NinjaDash folder (couldn't find backend/ and frontend/ next to deploy/)."
command -v pacman >/dev/null || die "This installer is for Arch Linux / CachyOS (pacman not found)."
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/backend/ninjadash/__init__.py")
INVOKER="${SUDO_USER:-}"

say "Installing NinjaDash $VERSION ($MODE mode)"

# ---- packages ---------------------------------------------------------------------
PKGS=(python curl)
case $MODE in
  kiosk)   PKGS+=(cage wlr-randr chromium inter-font noto-fonts) ;;
  desktop) PKGS+=(chromium inter-font noto-fonts) ;;
esac
say "Installing packages: ${PKGS[*]}"
pacman -S --needed --noconfirm "${PKGS[@]}" || die "Installing packages failed. Update the system first (sudo pacman -Syu), then run this again."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || die "Python 3.11 or newer is needed."
ok "Packages ready"

# ---- users ------------------------------------------------------------------------
if ! id ninjadash &>/dev/null; then
  useradd --system --home-dir /var/lib/ninjadash --no-create-home --shell /usr/bin/nologin \
          --comment "NinjaDash backend" ninjadash
  ok "Created system user ninjadash"
fi

# ---- program files ------------------------------------------------------------------
say "Copying program files to $PREFIX"
install -d -m 755 "$PREFIX"
rm -rf "$PREFIX/backend" "$PREFIX/frontend" "$PREFIX/deploy"
cp -r "$SRC/backend" "$SRC/frontend" "$SRC/deploy" "$PREFIX/"
find "$PREFIX" -name '__pycache__' -prune -exec rm -rf {} +
chown -R root:root "$PREFIX"
chmod -R u=rwX,go=rX "$PREFIX"
chmod 755 "$PREFIX/deploy/kiosk/kiosk.sh" "$PREFIX/deploy/kiosk/screen-agent.sh" "$PREFIX/deploy/install.sh" \
          "$PREFIX/deploy/uninstall.sh" "$PREFIX/deploy/setup-rdp.sh"
python3 -m compileall -q "$PREFIX/backend" >/dev/null || true
install -m 755 "$SRC/deploy/ninjadash" /usr/local/bin/ninjadash
ok "Installed to $PREFIX, helper command: ninjadash"

# ---- settings -----------------------------------------------------------------------
say "Settings in $ETC"
install -d -m 750 -o root -g ninjadash "$ETC"
if [[ ! -f $ETC/ninjadash.env ]]; then
  DEV_ENV=""
  [[ -n $INVOKER ]] && DEV_ENV="$(getent passwd "$INVOKER" | cut -d: -f6)/.config/ninjadash/ninjadash.env"
  if [[ -n $DEV_ENV && -f $DEV_ENV ]] && grep -Eq '^NINJA_CLIENT_SECRET=.+' "$DEV_ENV"; then
    install -m 640 -o root -g ninjadash "$DEV_ENV" "$ETC/ninjadash.env"
    ok "Copied your filled-in settings from $DEV_ENV"
  else
    install -m 640 -o root -g ninjadash "$SRC/config/.env.example" "$ETC/ninjadash.env"
    warn "Created $ETC/ninjadash.env. The API client is still empty, so the dashboard shows example data."
  fi
else
  chown root:ninjadash "$ETC/ninjadash.env"; chmod 640 "$ETC/ninjadash.env"
  ok "Kept your existing $ETC/ninjadash.env"
fi
if [[ ! -f $ETC/classify.toml ]]; then
  install -m 640 -o root -g ninjadash "$SRC/deploy/classify.local.toml" "$ETC/classify.toml"
  ok "Created $ETC/classify.toml for your own alert rules"
fi

PORT=$(sed -n 's/^LISTEN=.*:\([0-9]\+\).*/\1/p' "$ETC/ninjadash.env" | tail -1)
PORT=${PORT:-8080}
URL="http://127.0.0.1:$PORT/"

# ---- Home Assistant screen control ----------------------------------------------------
if [[ -z $(sed -n 's/^SCREEN_TOKEN=//p' "$ETC/ninjadash.env" | tail -1) ]]; then
  setenv SCREEN_TOKEN "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  ok "Created a secret token for screen control"
fi
LISTEN_NOW=$(sed -n 's/^LISTEN=//p' "$ETC/ninjadash.env" | tail -1)
if [[ $LISTEN_NOW == 0.0.0.0:* ]]; then
  HA_ON=1
elif [[ $HA == 1 ]] || { [[ -z $HA && $ASSUME_YES == 0 && -t 0 && $MODE != backend ]] && \
     ask "Let Home Assistant switch the screen on and off over the network?"; }; then
  setenv LISTEN "0.0.0.0:$PORT"
  setenv REMOTE_ACCESS screen
  HA_ON=1
  ok "Home Assistant can switch the screen (port $PORT; other PCs can only use the screen switch, with the token)"
else
  HA_ON=0
fi
[[ $HA_ON == 1 ]] && open_port "$PORT"

# ---- backend service ----------------------------------------------------------------
say "Starting the dashboard service"
install -m 644 "$SRC/deploy/systemd/ninjadash.service" /etc/systemd/system/ninjadash.service
systemctl daemon-reload
systemctl enable ninjadash.service >/dev/null 2>&1
systemctl restart ninjadash.service
for _ in $(seq 1 20); do curl -fs -o /dev/null --max-time 2 "${URL}healthz" && break; sleep 1; done
if curl -fs -o /dev/null --max-time 2 "$URL"; then
  ok "Dashboard is running on $URL"
else
  warn "The service did not answer yet. Check with: sudo ninjadash status"
fi

# ---- display -------------------------------------------------------------------------
REBOOT=0
case $MODE in
  kiosk)
    say "Setting up the kiosk screen"
    if ! id ninjadash-kiosk &>/dev/null; then
      useradd --system --create-home --home-dir /var/lib/ninjadash-kiosk --shell /usr/bin/nologin \
              --comment "NinjaDash kiosk screen" ninjadash-kiosk
      ok "Created system user ninjadash-kiosk"
    fi
    for g in video render input; do getent group "$g" >/dev/null && usermod -aG "$g" ninjadash-kiosk; done
    install -m 644 "$SRC/deploy/pam/ninjadash-kiosk" /etc/pam.d/ninjadash-kiosk
    sed "s#^Environment=NINJADASH_URL=.*#Environment=NINJADASH_URL=$URL#" \
      "$SRC/deploy/systemd/ninjadash-kiosk.service" > /etc/systemd/system/ninjadash-kiosk.service
    chmod 644 /etc/systemd/system/ninjadash-kiosk.service

    if [[ -L /etc/systemd/system/display-manager.service ]]; then
      DM=$(basename "$(readlink -f /etc/systemd/system/display-manager.service)")
      warn "A desktop login screen is enabled ($DM). The kiosk needs the screen for itself."
      if ask "Disable $DM so the dashboard starts at boot instead of the desktop?"; then
        systemctl disable "$DM" >/dev/null 2>&1
        echo "$DM" > "$ETC/.disabled-display-manager"
        ok "Disabled $DM (re-enable later with: sudo systemctl enable $DM)"
      else
        warn "Kept the desktop. Kiosk not enabled. Tip: sudo $0 --desktop <your user>"
        systemctl daemon-reload
        MODE=backend
      fi
    fi
    if [[ $MODE == kiosk ]]; then
      systemctl set-default multi-user.target >/dev/null
      systemctl daemon-reload
      systemctl enable ninjadash-kiosk.service >/dev/null 2>&1
      ok "Kiosk enabled: the dashboard opens full screen on the TV at every boot"
      REBOOT=1
    fi
    ;;
  desktop)
    say "Adding the dashboard to $DESKTOP_USER's desktop autostart"
    HOME_DIR=$(getent passwd "$DESKTOP_USER" | cut -d: -f6)
    [[ -n $HOME_DIR && -d $HOME_DIR ]] || die "User $DESKTOP_USER not found"
    install -d -o "$DESKTOP_USER" -g "$(id -gn "$DESKTOP_USER")" "$HOME_DIR/.config/autostart"
    cat > "$HOME_DIR/.config/autostart/ninjadash.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=NinjaDash
Comment=NinjaOne wall dashboard
Exec=env NINJADASH_URL=$URL /opt/ninjadash/deploy/kiosk/kiosk.sh
X-GNOME-Autostart-enabled=true
X-KDE-autostart-after=panel
EOF
    chown "$DESKTOP_USER":"$(id -gn "$DESKTOP_USER")" "$HOME_DIR/.config/autostart/ninjadash.desktop"
    ok "Chromium opens the dashboard full screen when $DESKTOP_USER logs in (Alt+F4 closes it)"
    ;;
esac

# ---- done ------------------------------------------------------------------------------
echo
say "Done."
if grep -Eq '^NINJA_CLIENT_SECRET=.+' "$ETC/ninjadash.env"; then
  echo "  Test the NinjaOne connection:   sudo ninjadash check"
else
  echo "  1. Add your NinjaOne API client: sudo ninjadash edit"
  echo "     (fill NINJA_CLIENT_ID and NINJA_CLIENT_SECRET, save)"
  echo "  2. Test the connection:          sudo ninjadash check"
  echo "  3. Apply it:                     sudo ninjadash restart"
fi
echo "  Dashboard in a browser on this PC: $URL"
echo "  Status / logs:                    sudo ninjadash status   ·   sudo ninjadash logs"
[[ $HA_ON == 1 ]] && echo "  Home Assistant configuration:     sudo ninjadash home-assistant"
echo "  Remote Desktop for maintenance:   sudo /opt/ninjadash/deploy/setup-rdp.sh"
[[ $REBOOT == 1 ]] && echo && echo "  Reboot to start the kiosk screen: sudo reboot"
exit 0
