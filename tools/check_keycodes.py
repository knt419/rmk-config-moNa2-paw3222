#!/usr/bin/env python3
"""Check every keycode referenced by keyboard.toml against RMK's keycode enums.

RMK's config parser rejects unknown key names at build time with a one-error-at-a-
time message, so this validates the whole file up front. The enum names are read
from the `rmk-types` source in the cargo registry.

Run:  python3 tools/check_keycodes.py
"""
from __future__ import annotations

import pathlib
import re
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = pathlib.Path.home() / ".cargo/registry/src"


def rmk_keycodes() -> set[str]:
    dirs = sorted(REGISTRY.glob("*/rmk-types-*"))
    if not dirs:
        raise SystemExit("rmk-types source not found in the cargo registry; run `cargo fetch` first")
    base = dirs[-1] / "src/keycode"
    names: set[str] = set()
    for f in base.glob("*.rs"):
        for m in re.finditer(r"pub enum \w+\s*\{(.*?)\n\}", f.read_text(), re.S):
            names |= set(re.findall(r"^    ([A-Za-z0-9_]+)\s*(?:=[^,\n]*)?,", m.group(1), re.M))
    names.discard("No")  # `No` is the no-op action, handled separately
    return names


MODIFIERS = {"LShift", "RShift", "LCtrl", "RCtrl", "LAlt", "RAlt", "LGui", "RGui"}
# Actions that are not HID keycodes
NON_HID = {"_", "No", "Bootloader", "CapsWord", "KeyRepeat", "Repeat", "GraveEscape",
           "ComboOn", "ComboOff", "ComboToggle", "Steno", "ToggleOutput"}
MULTI_ARG = {"WM", "MT", "TH", "LT", "LM", "MOD", "OSM", "MO", "OSL", "TT", "TG", "TO",
             "DF", "PDF", "SHIFTED", "TD", "MORSE", "MACRO", "STN"}


def split_top(expr: str) -> list[str]:
    """Split an action expression into (name, args) honouring nesting."""
    out, cur, depth = [], [], 0
    for ch in expr:
        if ch == "(":
            depth += 1
            if depth == 1:
                out.append("".join(cur).strip())
                cur = []
                continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                out.append("".join(cur).strip())
                cur = []
                continue
        if ch == "," and depth == 1:
            out.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return [p for p in out if p]


def tokenize(text: str) -> list[str]:
    """Split keymap text on whitespace outside parentheses."""
    out, cur, depth = [], [], 0
    for ch in text:
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            cur.append(ch)
        elif ch.isspace() and depth == 0:
            if cur:
                out.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


def walk(expr: str, known: set[str], bad: list[tuple[str, str]], where: str) -> None:
    expr = expr.strip()
    if not expr or expr in {"_", "No"}:
        return
    parts = split_top(expr)
    head = parts[0]
    if len(parts) == 1:
        if re.fullmatch(r"[A-Za-z]+(\|[A-Za-z]+)+", head):
            for mod in head.split("|"):
                if mod not in MODIFIERS:
                    bad.append((where, expr))
            return
        if head in NON_HID or re.fullmatch(r"User\d+", head):
            return
        if head not in known:
            bad.append((where, expr))
        return
    # Which arguments of each action hold a nested action expression.
    nested = {
        "WM": [0], "MT": [0], "TH": [0, 1], "LT": [1], "SHIFTED": [0],
        "LM": [], "MOD": [], "OSM": [], "MO": [], "OSL": [], "TT": [], "TG": [],
        "TO": [], "DF": [], "PDF": [], "TD": [], "MORSE": [], "MACRO": [], "STN": [],
    }
    if head in nested:
        for idx in nested[head]:
            if idx < len(parts) - 1:
                walk(parts[1 + idx], known, bad, where)
        return
    if head.upper() in MULTI_ARG or head in MULTI_ARG:
        return
    bad.append((where, expr))


def main() -> None:
    known = rmk_keycodes()
    cfg = tomllib.loads((ROOT / "keyboard.toml").read_text())
    bad: list[tuple[str, str]] = []

    for layer in cfg["keymap"]["layer"]:
        for tok in tokenize(layer["keys"]):
            walk(tok, known, bad, f'layer {layer["name"]}')
        for pair in layer.get("encoders", []):
            for tok in pair:
                walk(tok, known, bad, f'encoder {layer["name"]}')

    for combo in cfg["behavior"]["combo"]["combos"]:
        for tok in combo["actions"]:
            walk(tok, known, bad, "combo action")
        walk(combo["output"], known, bad, "combo output")

    for macro in cfg["behavior"]["macro"]["macros"]:
        for op in macro["operations"]:
            walk(op.get("keycode", ""), known, bad, "macro")

    for fork in cfg["behavior"].get("fork", {}).get("forks", []):
        for field in ("trigger", "negative_output", "positive_output"):
            walk(fork[field], known, bad, f"fork {field}")

    if bad:
        print(f"{len(bad)} unknown keycode reference(s):")
        for where, expr in bad:
            print(f"  - {where}: {expr}")
        raise SystemExit(1)
    print(f"all keycodes OK ({len(known)} names available)")


if __name__ == "__main__":
    main()
