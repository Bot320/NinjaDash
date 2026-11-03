#!/usr/bin/env bash
# Remote Desktop (RDP) for maintenance on the NinjaDash mini PC.
#
#   sudo ./deploy/setup-rdp.sh            set up RDP for the user who runs sudo
#   sudo ./deploy/setup-rdp.sh --user NAME
#
# Connect with any RDP client (Windows "Remote Desktop Connection", Remmina, the Microsoft
# Remote Desktop app) to the mini PC's address and log in with that Linux user's password.
# You get your own XFCE desktop. The TV keeps showing the dashboard meanwhile.
#
# Why XFCE and not KDE: RDP here runs on xrdp, which needs an X11 desktop, and KDE Plasma 6.8
# is Wayland-only. To see KDE on the TV itself, run `sudo ninjadash desktop` from the RDP session
# (and `sudo ninjadash kiosk` to go back).
set -euo pipefail

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }

RDP_USER="${SUDO_USER:-}"
ORIG_ARGS=("$@")
while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) RDP_USER="${2:-}"; shift ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done
[[ $EUID -eq 0 ]] || exec sudo -- bash "$0" "${ORIG_ARGS[@]}"
[[ -n $RDP_USER && $RDP_USER != root ]] || die "Run this with sudo from your normal user account (or pass --user NAME)."
id "$RDP_USER" &>/dev/null || die "User $RDP_USER does not exist."
HOME_DIR=$(getent passwd "$RDP_USER" | cut -d: -f6)
GROUP=$(id -gn "$RDP_USER")

say "Installing the XFCE desktop for Remote Desktop sessions"
pacman -S --needed --noconfirm xorg-server xfce4-session xfwm4 xfce4-panel xfdesktop xfce4-settings \
  xfce4-terminal thunar base-devel git \
  || die "Installing packages failed. Update the system first (sudo pacman -Syu), then run this again."
ok "XFCE installed"

say "Installing xrdp + xorgxrdp from the AUR (this compiles, takes a few minutes)"
if pacman -Q xrdp xorgxrdp &>/dev/null; then
  ok "xrdp and xorgxrdp are already installed"
else
  # --nocheck: xrdp 0.10.6.1's unit tests 7-10 (login-screen bitmap scaling, test_bitmap_load.c) fail
  # with the current imlib2 on Arch. Known on the AUR page since 2026-09; xrdp itself works fine.
  if command -v paru >/dev/null; then
    sudo -u "$RDP_USER" paru -S --needed --noconfirm --skipreview --nocheck xrdp xorgxrdp
  elif command -v yay >/dev/null; then
    sudo -u "$RDP_USER" yay -S --needed --noconfirm --answerdiff None --answerclean None --mflags --nocheck xrdp xorgxrdp
  else
    die "No AUR helper found. Install one first: sudo pacman -S paru"
  fi
  pacman -Q xrdp xorgxrdp &>/dev/null || die "xrdp/xorgxrdp did not install. Scroll up for the build error."
  ok "xrdp installed"
fi

say "Setting up the RDP session for $RDP_USER"
XINITRC="$HOME_DIR/.xinitrc"
if [[ -f $XINITRC ]] && ! grep -q "ninjadash-rdp" "$XINITRC"; then
  cp "$XINITRC" "$XINITRC.before-ninjadash"
  warn "Saved your old ~/.xinitrc as ~/.xinitrc.before-ninjadash"
fi
cat > "$XINITRC" <<'EOF'
#!/bin/sh
# ninjadash-rdp: desktop for Remote Desktop (xrdp) sessions. Also used by `startx`.
export XDG_SESSION_TYPE=x11
export XDG_CURRENT_DESKTOP=XFCE
export DESKTOP_SESSION=xfce
exec dbus-run-session startxfce4
EOF
chown "$RDP_USER:$GROUP" "$XINITRC"
chmod 644 "$XINITRC"
ok "~/.xinitrc starts XFCE"

systemctl enable --now xrdp.service xrdp-sesman.service >/dev/null 2>&1 || systemctl enable --now xrdp.service
systemctl is-active --quiet xrdp.service && ok "xrdp is running on port 3389" || warn "xrdp did not start: journalctl -u xrdp -u xrdp-sesman"

if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 3389/tcp >/dev/null && ok "Firewall (ufw): opened port 3389"
elif command -v firewall-cmd >/dev/null && systemctl is-active --quiet firewalld; then
  firewall-cmd --permanent --add-port=3389/tcp >/dev/null && firewall-cmd --reload >/dev/null && ok "Firewall (firewalld): opened port 3389"
fi

IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="src") print $(i+1)}')
echo
TARGET=${IP:-the address of this PC}
say "Done. Connect with Remote Desktop to $TARGET and log in as $RDP_USER."
echo "  In the RDP session, open a terminal for:"
echo "    sudo ninjadash logs       watch the dashboard log"
echo "    sudo ninjadash desktop    show KDE on the TV instead of the dashboard"
echo "    sudo ninjadash kiosk      back to the dashboard on the TV"
echo "  Only use RDP inside your own network (or over a VPN). Don't forward port 3389 on your router."
