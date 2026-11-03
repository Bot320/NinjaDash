#!/usr/bin/env bash
# Follows the screen on/off state that Home Assistant sets in NinjaDash and switches the video
# output to match. Started by kiosk.sh inside the kiosk (cage) or the desktop session.
#   cage (kiosk):  wlr-randr --output <name> --off / --on   (cuts the HDMI signal; most TVs then sleep)
#   KDE desktop:   kscreen-doctor --dpms off / on
# If neither works, the dashboard page still goes black on its own.
BASE="${NINJADASH_URL:-http://127.0.0.1:8080/}"
STATE_URL="${BASE}api/screen?agent=1"
applied=""

outputs() { wlr-randr 2>/dev/null | awk '/^[^ \t]/ {print $1}'; }

switch() {   # $1 = on | off
  if [[ -z ${XDG_CURRENT_DESKTOP:-} ]] && command -v wlr-randr >/dev/null; then
    local ok=1 o
    for o in $(outputs); do wlr-randr --output "$o" --"$1" && ok=0; done
    return $ok
  elif command -v kscreen-doctor >/dev/null; then
    kscreen-doctor --dpms "$1" >/dev/null 2>&1
  else
    return 1
  fi
}

while sleep 2; do
  state=$(curl -fs --max-time 2 "$STATE_URL") || continue
  if [[ $state == *'"on": false'* || $state == *'"on":false'* ]]; then want=off; else want=on; fi
  [[ $want == "$applied" ]] && continue
  if switch "$want"; then
    echo "screen-agent: screen $want"
  else
    echo "screen-agent: could not switch the output $want (the page is blacked out instead)"
  fi
  applied=$want
done
