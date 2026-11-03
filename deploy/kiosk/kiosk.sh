#!/usr/bin/env bash
# Opens the dashboard full screen in Chromium. Used by the kiosk service (inside cage)
# and by the desktop autostart entry.
URL="${NINJADASH_URL:-http://127.0.0.1:8080/}"

# Wait up to 90 s for the backend, so the screen never shows a "can't connect" page.
for _ in $(seq 1 90); do
  curl -fs -o /dev/null --max-time 2 "${URL}healthz" && break
  curl -fs -o /dev/null --max-time 2 "$URL" && break
  sleep 1
done

# Screen on/off from Home Assistant (switches the HDMI output). Ends together with this session.
"$(dirname "$(readlink -f "$0")")/screen-agent.sh" &

PROFILE="${HOME:-/tmp}/.ninjadash-chromium"
mkdir -p "$PROFILE"

# English browser UI and page language, so Chromium never offers to translate the (English) dashboard
# on a German system. LANGUAGE only affects Chromium here, not the rest of the PC.
export LANGUAGE=en

exec chromium \
  --kiosk "$URL" \
  --accept-lang=en-US,en \
  --incognito \
  --user-data-dir="$PROFILE" \
  --no-first-run \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-translate \
  --disable-sync \
  --disable-features=Translate,MediaRouter,HardwareMediaKeyHandling \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  --password-store=basic \
  --check-for-update-interval=31536000 \
  --disk-cache-size=33554432 \
  --renderer-process-limit=2 \
  --ozone-platform-hint=auto
