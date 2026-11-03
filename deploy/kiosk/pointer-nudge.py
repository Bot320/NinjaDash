#!/usr/bin/env python3
"""Hides the mouse pointer on the kiosk screen.

Chromium only applies the page's `cursor: none` after the first mouse movement, so the pointer
stays visible after boot until someone touches the mouse. This service creates a short-lived
virtual mouse through the kernel (/dev/uinput), moves it 2 px right and back, and removes it:
  - once the kiosk browser has loaded the dashboard
  - whenever the kiosk browser restarts
  - when the screen is switched back on (Home Assistant / `ninjadash screen on`)
Nothing is clicked. Runs as root (ninjadash-pointer.service), needs no extra packages.

  pointer-nudge.py          run as a service (wait, nudge, keep watching)
  pointer-nudge.py --once   nudge one time now
"""
from __future__ import annotations

import fcntl
import json
import os
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

# From <linux/uinput.h> / <linux/input-event-codes.h> (checked against the kernel headers)
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_RELBIT = 0x40045564, 0x40045565, 0x40045566
UI_DEV_SETUP, UI_DEV_CREATE, UI_DEV_DESTROY = 0x405C5503, 0x5501, 0x5502
EV_SYN, EV_KEY, EV_REL, SYN_REPORT = 0, 1, 2, 0
REL_X, REL_Y, BTN_LEFT, BTN_RIGHT = 0, 1, 0x110, 0x111
BUS_VIRTUAL = 0x06
SETUP_FORMAT = "<HHHH80sI"          # struct uinput_setup: input_id, name[80], ff_effects_max (92 bytes)
EVENT_FORMAT = "llHHi"              # struct input_event: timeval, type, code, value (24 bytes on 64-bit)

KIOSK_USER = "ninjadash-kiosk"
BASE = os.environ.get("NINJADASH_URL", "http://127.0.0.1:8080/")


def log(msg: str) -> None:
    print(f"pointer-nudge: {msg}", flush=True)


def setup_struct(name: str = "NinjaDash pointer nudge") -> bytes:
    return struct.pack(SETUP_FORMAT, BUS_VIRTUAL, 0x1209, 0x0001, 1, name.encode()[:79], 0)


def event(type_: int, code: int, value: int) -> bytes:
    return struct.pack(EVENT_FORMAT, 0, 0, type_, code, value)


def nudge() -> bool:
    if not os.path.exists("/dev/uinput"):
        subprocess.run(["modprobe", "uinput"], check=False)
    try:
        fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
    except OSError as e:
        log(f"cannot open /dev/uinput: {e}")
        return False
    try:
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
        fcntl.ioctl(fd, UI_SET_KEYBIT, BTN_LEFT)          # needed so it counts as a mouse
        fcntl.ioctl(fd, UI_SET_KEYBIT, BTN_RIGHT)
        fcntl.ioctl(fd, UI_SET_EVBIT, EV_REL)
        fcntl.ioctl(fd, UI_SET_RELBIT, REL_X)
        fcntl.ioctl(fd, UI_SET_RELBIT, REL_Y)
        fcntl.ioctl(fd, UI_DEV_SETUP, setup_struct())
        fcntl.ioctl(fd, UI_DEV_CREATE)
        time.sleep(1.5)                                     # let udev, libinput and cage pick it up
        for dx in (2, -2):
            os.write(fd, event(EV_REL, REL_X, dx) + event(EV_SYN, SYN_REPORT, 0))
            time.sleep(0.15)
        time.sleep(0.5)
        fcntl.ioctl(fd, UI_DEV_DESTROY)
        log("moved the pointer to hide it")
        return True
    except OSError as e:
        log(f"virtual mouse failed: {e}")
        return False
    finally:
        os.close(fd)


def browser_pid() -> str | None:
    r = subprocess.run(["pgrep", "-o", "-u", KIOSK_USER, "chromium"], capture_output=True, text=True)
    return r.stdout.strip() or None


def screen_on() -> bool | None:
    try:
        with urllib.request.urlopen(BASE + "api/screen", timeout=2) as resp:
            return bool(json.load(resp).get("on", True))
    except Exception:
        return None


def page_ready() -> bool:
    try:
        with urllib.request.urlopen(BASE + "healthz", timeout=2):
            return True
    except urllib.error.HTTPError:
        return True                    # 503 = no recent NinjaOne sync, but the page is served
    except Exception:
        return False


def watch() -> None:
    nudged_for = None
    last_screen = True
    while True:
        pid = browser_pid()
        if pid and pid != nudged_for and page_ready():
            time.sleep(8)                                   # Chromium starts, loads and draws the page
            if browser_pid() == pid:
                nudge()
                nudged_for = pid
        on = screen_on()
        if on is True and last_screen is False:
            time.sleep(3)                                   # output back on, browser redrawn
            nudge()
        if on is not None:
            last_screen = on
        time.sleep(3)


if __name__ == "__main__":
    if "--once" in sys.argv:
        sys.exit(0 if nudge() else 1)
    watch()
