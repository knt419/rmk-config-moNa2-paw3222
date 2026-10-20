#!/usr/bin/env python3
"""Render the default keymap as ASCII diagrams in README.md.

Positions come from the board itself: `mona2.dtsi` lists the physical layout keys
(x/y in 0.01u) and the matrix transform in the *same* order, so zipping them maps
every (row, col) to a physical slot. Key labels come from `keyboard.toml`, so the
diagrams cannot drift from the firmware config.

Run:  python3 tools/keymap_diagram.py          # rewrites the README section
      python3 tools/keymap_diagram.py --print  # just print
"""
from __future__ import annotations

import pathlib
import re
import sys
import tomllib

ZMK = pathlib.Path("/home/knt419/Projects/zmk-for-moNa2-paw3222")
DTSI = ZMK / "boards/shields/mona2/mona2.dtsi"
ROOT = pathlib.Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

START = "<!-- keymap-diagram:start -->"
END = "<!-- keymap-diagram:end -->"

CELL = 9  # chars per key cell

# Readable short forms for keys whose RMK name is long.
NAMES = {
    "MouseBtn1": "LClk", "MouseBtn2": "RClk", "MouseBtn3": "MClk",
    "Backspace": "BkSp", "CapsLock": "Caps", "Semicolon": ";", "Quote": "'",
    "LeftBracket": "[", "RightBracket": "]", "Backslash": "\\", "Grave": "`",
    "Comma": ",", "Dot": ".", "Slash": "/", "Minus": "-", "Equal": "=",
    "Enter": "Ent", "Escape": "Esc", "Space": "Spc", "Tab": "Tab",
    "PrintScreen": "PrtS", "NumLock": "NumL", "PageUp": "PgU", "PageDown": "PgD",
    "ScrollLock": "ScrL", "Pause": "Paus", "MediaPrevTrack": "MPrev",
    "MediaNextTrack": "MNext", "MediaPlayPause": "MPlay", "MediaStop": "MStop",
    # bare modifier keycodes are easier as one glyph inside tap/hold labels
    "LShift": "S", "RShift": "S", "LCtrl": "^", "RCtrl": "^",
    "LAlt": "A", "RAlt": "A", "LGui": "G", "RGui": "G",
    "Language1": "かな", "Language2": "英数", "Application": "Menu",
    "Bootloader": "Boot", "AudioVolDown": "Vol-", "AudioVolUp": "Vol+",
    "International1": "I1", "International3": "I3", "Delete": "Del",
    "Insert": "Ins", "Left": "Left", "Right": "Rght", "Up": "Up", "Down": "Down",
    "F13": "F13", "F14": "F14", "F15": "F15", "F16": "F16",
}
MODS = {"LShift": "S", "RShift": "S", "LCtrl": "^", "RCtrl": "^",
        "LAlt": "A", "RAlt": "A", "LGui": "G", "RGui": "G"}
# SHIFTED(x) rendered as the glyph a real keyboard would show.
SHIFTED = {
    "Kc1": "!", "Kc2": "@", "Kc3": "#", "Kc4": "$", "Kc5": "%", "Kc6": "^",
    "Kc7": "&", "Kc8": "*", "Kc9": "(", "Kc0": ")", "Minus": "_", "Equal": "+",
    "LeftBracket": "{", "RightBracket": "}", "Backslash": "|", "Semicolon": ":",
    "Quote": '"', "Slash": "?", "Grave": "~", "International1": "I1S",
    "International3": "I3S",
}


def key_positions() -> list[tuple[tuple[int, int], int, int]]:
    """[((row, col), x, y)] by zipping the ZMK transform with its physical layout."""
    text = DTSI.read_text()
    layout = re.search(r"physical_layout0:.*?keys\s*(.*?);", text, re.S).group(1)
    coords = [
        (int(m.group(1)), int(m.group(2)))
        for m in re.finditer(r"key_physical_attrs\s+\d+\s+\d+\s+(-?\d+)\s+(-?\d+)", layout)
    ]
    transform = re.search(r"default_transform:.*?map = <(.*?)>;", text, re.S).group(1)
    cells = [(int(r), int(c)) for r, c in re.findall(r"RC\((\d+),(\d+)\)", transform)]
    if len(coords) != len(cells):
        raise SystemExit(f"layout has {len(coords)} keys, transform has {len(cells)}")
    return [(cell, x, y) for cell, (x, y) in zip(cells, coords)]


def split_args(expr: str) -> list[str]:
    """Split `NAME(a, b, c)` into [NAME, a, b, c] honouring nesting."""
    out, cur, depth = [], [], 0
    for ch in expr:
        if ch == "(":
            depth += 1
            if depth == 1:
                out.append("".join(cur).strip())
                cur = []
                continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                out.append("".join(cur).strip())
                cur = []
                continue
        elif ch == "," and depth == 1:
            out.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return [p for p in out if p]


def pretty(expr: str) -> str:
    expr = expr.strip()
    if expr in {"_", ""}:
        return "_"
    if expr == "No":
        return "·"

    parts = split_args(expr)
    head, args = parts[0], parts[1:]
    if head == "TH":
        return f"{pretty(args[0])}/{pretty(args[1])}"
    if head == "MT":
        return f"{pretty(args[0])}/{MODS.get(args[1], args[1])}"
    if head == "LT":
        return f"{pretty(args[1])}/{args[0]}"
    if head == "WM":
        mods = "".join(MODS.get(p, "?") for p in args[1].split("|"))
        return f"{pretty(args[0])}{mods}"
    if head == "SHIFTED":
        return SHIFTED.get(args[0], f"S{pretty(args[0])}")
    if head == "MACRO":
        return f"M{args[0]}"
    if re.fullmatch(r"User\d+", head):
        return f"U{head[4:]}"
    if head == "MO":
        return f"MO{args[0]}"
    return NAMES.get(head, head)


def fit(label: str) -> str:
    room = CELL - 1
    return (label if len(label) <= room else label[:room]).ljust(CELL)


def render(layer: dict, slots: list[tuple[tuple[int, int], int, int]]) -> str:
    keys = layer["keys"].replace("\n", " ")
    # Re-tokenise: actions contain spaces, so split with the same paren-aware walk.
    tokens, depth, cur = [], 0, []
    for ch in keys:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch.isspace() and depth == 0:
            if cur:
                tokens.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        tokens.append("".join(cur))
    if len(tokens) != 44:
        raise SystemExit(f'{layer["name"]}: expected 44 keys, got {len(tokens)}')

    cols = 11
    placed: dict[tuple[int, int], str] = {}
    for (r, c), x, y in slots:
        placed[(y // 100, x // 100)] = pretty(tokens[r * cols + c])

    xs = sorted({x // 100 for _c, x, _y in slots})
    ys = sorted({y // 100 for _c, _x, y in slots})
    left = [x for x in xs if x <= 5]
    right = [x for x in xs if x >= 7]

    lines = []
    for y in ys:
        cells = [fit(placed.get((y, x), "")) for x in left]
        cells.append("  ")
        cells += [fit(placed.get((y, x), "")) for x in right]
        lines.append("   " + "".join(cells).rstrip())
    return "\n".join(lines)


def main() -> None:
    cfg = tomllib.loads((ROOT / "keyboard.toml").read_text())
    slots = key_positions()
    layers = cfg["keymap"]["layer"]

    parts = [
        "<!-- keymap-diagram:start -->",
        "Generated by `tools/keymap_diagram.py` from `keyboard.toml`; positions come from the "
        "ZMK physical layout in `mona2.dtsi`.",
        "",
        "`_` transparent · `·` no key · `tap/hold` = tap on tap, hold on hold · "
        "`key/N` = layer-tap to layer *N* · `key^` = key+Ctrl, `keyS` = key+Shift, `keyG` = "
        "key+Gui, `keyA` = key+Alt · "
        "the left block is the left half (6 columns), the right block is the right half; its "
        "leftmost column is the inner thumb column (populated on the middle rows only).",
        "",
    ]
    for layer in layers:
        parts.append(f"**{layer['name']}**")
        parts.append("")
        parts.append("```")
        parts.append(render(layer, slots))
        parts.append("```")
        parts.append("")
    parts.append(END)
    rendered = "\n".join(parts)

    if "--print" in sys.argv:
        print(rendered)
        return

    text = README.read_text()
    if START in text and END in text:
        text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _m: rendered, text, flags=re.S)
    else:
        raise SystemExit("README has no keymap-diagram markers to fill")
    README.write_text(text)
    print(f"README.md: keymap diagrams updated ({len(layers)} layers)")


if __name__ == "__main__":
    main()
