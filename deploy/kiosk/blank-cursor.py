#!/usr/bin/env python3
"""Writes an invisible X cursor theme, used only by the kiosk (XCURSOR_THEME=ninjadash-blank).

cage shows its pointer from the first frame and has no option to hide it, so the kiosk gets a
pointer theme whose every cursor is a single transparent pixel. Your own desktop is unaffected.

Usage: blank-cursor.py /usr/share/icons/ninjadash-blank
"""
import struct
import sys
from pathlib import Path

NAMES = """left_ptr default arrow top_left_arrow pointer hand1 hand2 text xterm ibeam vertical-text
wait watch progress left_ptr_watch half-busy crosshair cross tcross move fleur grab grabbing openhand
closedhand dnd-move all-scroll not-allowed no-drop crossed_circle forbidden help question_arrow whats_this
context-menu cell copy alias link col-resize row-resize ew-resize ns-resize nesw-resize nwse-resize
sb_h_double_arrow sb_v_double_arrow n-resize s-resize e-resize w-resize ne-resize nw-resize se-resize
sw-resize top_side bottom_side left_side right_side top_left_corner top_right_corner bottom_left_corner
bottom_right_corner zoom-in zoom-out X_cursor pirate dnd-none dnd-copy dnd-link""".split()

IMAGE = 0xFFFD0002


def xcursor(nominal: int = 24) -> bytes:
    """Xcursor file with one 1x1 fully transparent image (format: libXcursor's xcursor.c)."""
    header = struct.pack("<4sIII", b"Xcur", 16, 0x10000, 1)
    toc = struct.pack("<III", IMAGE, nominal, 16 + 12)
    image = struct.pack("<IIIIIIIII", 36, IMAGE, nominal, 1, 1, 1, 0, 0, 0) + struct.pack("<I", 0)
    return header + toc + image


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/share/icons/ninjadash-blank")
    cursors = target / "cursors"
    cursors.mkdir(parents=True, exist_ok=True)
    (target / "index.theme").write_text("[Icon Theme]\nName=NinjaDash blank\nComment=Invisible pointer for the NinjaDash kiosk\n")
    (cursors / "left_ptr").write_bytes(xcursor())
    for name in NAMES[1:]:
        link = cursors / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to("left_ptr")
    print(f"Invisible cursor theme written to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
