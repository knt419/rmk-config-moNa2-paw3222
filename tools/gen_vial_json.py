#!/usr/bin/env python3
"""Generate vial.json (Vial keyboard definition) for the moNa2 RMK firmware.

Every key carries its matrix position as the KLE label ("row,col"), which is how
Vial associates a key with a keymap slot. Keys are emitted in the same row-major
order as `[keymap.layer].keys`, so Vial indices line up with RMK's.

Run:  python3 tools/gen_vial_json.py
"""
from __future__ import annotations

import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parents[1] / "vial.json"
ROWS, COLS = 4, 11

# Vial custom keycodes are just labels for `UserN`; RMK uses:
#   User0..4  select BLE profile N          User5/6  next/previous profile
#   User7     clear current bond            User8    toggle USB/BLE output
CUSTOM_KEYCODES = [
    {"name": "BLE", "title": "Switch to BLE profile 0", "shortName": "BT0"},
    {"name": "BLE", "title": "Switch to BLE profile 1", "shortName": "BT1"},
    {"name": "BLE", "title": "Switch to BLE profile 2", "shortName": "BT2"},
    {"name": "BLE", "title": "Switch to BLE profile 3", "shortName": "BT3"},
    {"name": "BLE", "title": "Switch to BLE profile 4", "shortName": "BT4"},
    {"name": "BLE", "title": "Next BLE profile", "shortName": "BT+"},
    {"name": "BLE", "title": "Previous BLE profile", "shortName": "BT-"},
    {"name": "BLE", "title": "Clear current bond", "shortName": "CLR"},
    {"name": "BLE", "title": "Toggle USB/BLE output", "shortName": "USB/BLE"},
]


def main() -> None:
    keymap = [[f"{r},{c}" for c in range(COLS)] for r in range(ROWS)]
    doc = {
        "name": "moNa2",
        "vendorId": "0x4c4b",
        "productId": "0x4e32",
        "matrix": {"rows": ROWS, "cols": COLS},
        "customKeycodes": CUSTOM_KEYCODES,
        "layouts": {"keymap": keymap},
    }
    OUT.write_text(json.dumps(doc, indent=2) + "\n")
    parsed = json.loads(OUT.read_text())
    n = sum(len(row) for row in parsed["layouts"]["keymap"])
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes), keys={n}")


if __name__ == "__main__":
    main()
