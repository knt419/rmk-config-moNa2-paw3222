#!/usr/bin/env python3
"""Port zmk-for-moNa2-paw3222 (ZMK) into an RMK 0.9 keyboard.toml keymap.

The ZMK keymap lists bindings in *matrix-transform* order; RMK wants a plain
row-major (row, col) grid, so the transform map from mona2.dtsi is used to place
every binding back onto its matrix position.

Run:  python3 tools/port_zmk_keymap.py
"""
from __future__ import annotations

import pathlib
import re

ZMK = pathlib.Path("/home/knt419/Projects/zmk-for-moNa2-paw3222")
DTSI = ZMK / "boards/shields/mona2/mona2.dtsi"
KEYMAP = ZMK / "config/mona2.keymap"
OUT = pathlib.Path(__file__).resolve().parents[1] / "keyboard.toml"

ROWS, COLS = 4, 11

# ---------------------------------------------------------------------------
# ZMK -> RMK keycode table
# ---------------------------------------------------------------------------
MODS = {"LS": "LShift", "LC": "LCtrl", "LA": "LAlt", "LG": "LGui"}

KEYS = {
    # letters
    **{c: c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
    # digits
    **{f"NUMBER_{i}": f"Kc{i}" for i in range(10)},
    **{f"N{i}": f"Kc{i}" for i in range(10)},
    **{f"KP_{i}": f"Kp{i}" for i in range(10)},
    # punctuation / named keys
    "MINUS": "Minus", "EQUAL": "Equal", "LEFT_BRACKET": "LeftBracket",
    "RIGHT_BRACKET": "RightBracket", "BACKSLASH": "Backslash", "SEMICOLON": "Semicolon",
    "SINGLE_QUOTE": "Quote", "GRAVE": "Grave", "COMMA": "Comma", "PERIOD": "Dot",
    "SLASH": "Slash", "CAPSLOCK": "CapsLock", "SPACE": "Space", "TAB": "Tab",
    "ENTER": "Enter", "BACKSPACE": "Backspace", "ESCAPE": "Escape", "ESC": "Escape",
    "DELETE": "Delete", "INSERT": "Insert", "HOME": "Home", "END": "End",
    "PAGE_UP": "PageUp", "PAGE_DOWN": "PageDown", "PRINTSCREEN": "PrintScreen",
    "PAUSE_BREAK": "Pause", "SCROLLLOCK": "ScrollLock", "KP_NUMLOCK": "NumLock",
    "KP_SLASH": "KpSlash", "KP_ASTERISK": "KpAsterisk", "KP_MINUS": "KpMinus",
    "KP_PLUS": "KpPlus", "KP_ENTER": "KpEnter", "KP_DOT": "KpDot",
    "LEFT_SHIFT": "LShift", "LSHIFT": "LShift", "RIGHT_SHIFT": "RShift", "RSHIFT": "RShift",
    "LEFT_CONTROL": "LCtrl", "LCTRL": "LCtrl", "RIGHT_CONTROL": "RCtrl", "RCTRL": "RCtrl",
    "LEFT_ALT": "LAlt", "LALT": "LAlt", "RIGHT_ALT": "RAlt", "RALT": "RAlt",
    "LEFT_GUI": "LGui", "LGUI": "LGui", "LEFT_WIN": "LGui", "RIGHT_GUI": "RGui",
    "LANGUAGE_1": "Language1", "LANGUAGE_2": "Language2",
    "LEFT": "Left", "LEFT_ARROW": "Left", "RIGHT": "Right", "RIGHT_ARROW": "Right",
    "UP": "Up", "UP_ARROW": "Up", "DOWN": "Down", "DOWN_ARROW": "Down",
    "K_CONTEXT_MENU": "Application",
    "C_VOLUME_UP": "AudioVolUp", "C_VOLUME_DOWN": "AudioVolDown",
    "C_PREV": "MediaPrevTrack", "C_NEXT": "MediaNextTrack",
    "C_PLAY_PAUSE": "MediaPlayPause", "C_STOP": "MediaStop",
    # JIS-related raw usages used through the JP_* defines
    "I1": "International1", "I3": "International3",
    # shifted symbols (RMK has no dedicated keycode for these)
    "EXCLAMATION": "SHIFTED(Kc1)", "AT": "SHIFTED(Kc2)", "HASH": "SHIFTED(Kc3)",
    "DOLLAR": "SHIFTED(Kc4)", "PERCENT": "SHIFTED(Kc5)", "CARET": "SHIFTED(Kc6)",
    "AMPERSAND": "SHIFTED(Kc7)", "ASTERISK": "SHIFTED(Kc8)",
    "LEFT_PARENTHESIS": "SHIFTED(Kc9)", "RIGHT_PARENTHESIS": "SHIFTED(Kc0)",
    "UNDER": "SHIFTED(Minus)", "PLUS": "SHIFTED(Equal)",
    "LEFT_BRACE": "SHIFTED(LeftBracket)", "RIGHT_BRACE": "SHIFTED(RightBracket)",
    "PIPE": "SHIFTED(Backslash)", "COLON": "SHIFTED(Semicolon)",
    "DOUBLE_QUOTES": "SHIFTED(Quote)", "QUESTION": "SHIFTED(Slash)",
    "TILDE": "SHIFTED(Grave)", "LESS_THAN": "SHIFTED(Comma)",
    "GREATER_THAN": "SHIFTED(Dot)",
    **{f"F{i}": f"F{i}" for i in range(1, 25)},
}

# `#define` aliases from the ZMK keymap: Japanese-layout meaning on the same key.
JP_ALIASES = {
    "JP_DOUBLE_QUOTES": "AT", "JP_AMPERSAND": "CARET", "JP_QUOTE": "AMPERSAND",
    "JP_EQUAL": "UNDER", "JP_CARET": "EQUAL", "JP_YEN": "I3", "JP_PLUS": "COLON",
    "JP_TILDE": "PLUS", "JP_PIPE": "LS(I3)", "JP_AT": "LEFT_BRACKET",
    "JP_COLON": "SINGLE_QUOTE", "JP_ASTERISK": "DOUBLE_QUOTES",
    "JP_BACKQUOTE": "LEFT_BRACE", "JP_UNDERSCORE": "LS(I1)",
    "JP_LEFT_BRACKET": "RIGHT_BRACKET", "JP_RIGHT_BRACKET": "BACKSLASH",
    "JP_LEFT_PARENTHESIS": "ASTERISK", "JP_RIGHT_PARENTHESIS": "LEFT_PARENTHESIS",
    "JP_LEFT_BRACE": "RIGHT_BRACE", "JP_RIGHT_BRACE": "PIPE",
    "JP_KANA": "LANGUAGE_1", "JP_EISU": "LANGUAGE_2", "JP_HANZEN": "GRAVE",
}

MOUSE = {"LCLK": "MouseBtn1", "RCLK": "MouseBtn2", "MCLK": "MouseBtn3",
         "MB1": "MouseBtn1", "MB2": "MouseBtn2", "MB3": "MouseBtn3"}

# RMK macros, as ZMK macro bodies expressed in RMK operations.
# ("tap"|"down"|"up", keycode-expression)
MACROS: dict[str, list[tuple[str, str]]] = {
    "winmvright": [("down", "LGui"), ("tap", "Right"), ("up", "LGui")],
    "winmvleft": [("down", "LGui"), ("tap", "Left"), ("up", "LGui")],
    "DBLSFT": [("tap", "LShift"), ("tap", "LShift")],
    "DBLCTL": [("tap", "LCtrl"), ("tap", "LCtrl")],
    "at": [("tap", "Language2"), ("tap", "SHIFTED(Kc2)")],
    "hash": [("tap", "Language2"), ("tap", "SHIFTED(Kc3)")],
    "amp": [("tap", "Language2"), ("tap", "SHIFTED(Kc7)")],
    "dollar": [("tap", "Language2"), ("tap", "SHIFTED(Kc4)")],
    "backquote": [("tap", "Language2"), ("tap", "Grave")],
    "quote": [("tap", "Language2"), ("tap", "Quote")],
    "doublequote": [("tap", "Language2"), ("tap", "SHIFTED(Quote)")],
    "caret": [("tap", "Language2"), ("tap", "SHIFTED(Kc6)")],
    "pipe": [("tap", "Language2"), ("tap", "SHIFTED(Backslash)")],
    "jp_at": [("tap", "Language2"), ("tap", "LeftBracket")],
    "jp_amp": [("tap", "Language2"), ("tap", "SHIFTED(Kc6)")],
    "jp_quote": [("tap", "Language2"), ("tap", "SHIFTED(Kc7)")],
    "jp_doublequote": [("tap", "Language2"), ("tap", "SHIFTED(Kc2)")],
    "jp_caret": [("tap", "Language2"), ("tap", "Equal")],
    "jp_pipe": [("tap", "Language2"), ("tap", "SHIFTED(International3)")],
    "jp_backquote": [("tap", "Language2"), ("tap", "SHIFTED(LeftBracket)")],
    "parenthesis": [("tap", "Language2"), ("tap", "SHIFTED(Kc9)"), ("tap", "SHIFTED(Kc0)"), ("tap", "Left")],
    "brackets": [("tap", "Language2"), ("tap", "LeftBracket"), ("tap", "RightBracket"), ("tap", "Left")],
    "braces": [("tap", "Language2"), ("tap", "SHIFTED(LeftBracket)"), ("tap", "SHIFTED(RightBracket)"), ("tap", "Left")],
    "zen_parenthesis": [("tap", "Language1"), ("tap", "SHIFTED(Kc9)"), ("tap", "SHIFTED(Kc0)"), ("tap", "Enter"), ("tap", "Left")],
    "zen_brackets": [("tap", "Language1"), ("tap", "LeftBracket"), ("tap", "RightBracket"), ("tap", "Enter"), ("tap", "Left")],
    "zen_braces": [("tap", "Language1"), ("tap", "SHIFTED(LeftBracket)"), ("tap", "SHIFTED(RightBracket)"), ("tap", "Enter"), ("tap", "Left")],
}

# Arity (number of arguments) per ZMK behavior instance used in this keymap.
ARITY = {
    "kp": 1, "trans": 0, "none": 0, "mt": 2, "lt": 2, "mo": 1, "to": 1, "tog": 1,
    "holdtap": 2, "imeonoff": 2, "lt_bsdel": 2, "mkp": 1, "mkp_layer": 2,
    "out": 1, "bt": 2, "ind_bat": 0, "ind_con": 0, "bootloader": 0, "slash": 0,
    "uj_backquote": 2, "uj_quote": 2, "uj_doublequote": 2, "uj_caret": 2,
    "uj_pipe": 2, "uj_at": 2, "uj_amp": 2,
    "paren": 2, "brack": 2, "brace": 2, "dblsft": 0,
    "DBLSFT": 0, "DBLCTL": 0, "winmvright": 0, "winmvleft": 0,
    **{name: 0 for name in MACROS if name not in {"winmvright", "winmvleft"}},
}


def read_transform() -> list[tuple[int, int]]:
    text = DTSI.read_text()
    m = re.search(r"default_transform:.*?map = <(.*?)>;", text, re.S)
    assert m, "transform map not found"
    pairs = re.findall(r"RC\((\d+),(\d+)\)", m.group(1))
    return [(int(r), int(c)) for r, c in pairs]


def read_layers() -> "dict[str, list[str]]":
    """Return {layer name: [binding token lists]} in transform order."""
    text = KEYMAP.read_text()
    layers: dict[str, list[str]] = {}
    for m in re.finditer(r"^\s{8}(\w+) \{\s*\n\s*bindings = <(.*?)>;", text, re.S | re.M):
        name, body = m.group(1), m.group(2)
        layers[name] = parse_bindings(body)
    return layers


def parse_bindings(body: str) -> list[list[str]]:
    """Split a ZMK `<...>` binding list into [behavior, *args] entries."""
    out: list[list[str]] = []
    for chunk in body.split("&")[1:]:
        toks = chunk.split()
        if not toks:
            continue
        behavior, args = toks[0], toks[1:]
        arity = ARITY[behavior]
        out.append([behavior] + (args[:arity] if arity else []))
    return out


# ---------------------------------------------------------------------------
# Translation: ZMK binding -> RMK action expression
# ---------------------------------------------------------------------------
MOD_ORDER = ["LCtrl", "LShift", "LAlt", "LGui"]


class Port:
    def __init__(self) -> None:
        self.macro_use: list[str] = []
        self.unknown: set[str] = set()

    def macro(self, name: str) -> str:
        if name not in MACROS:
            raise KeyError(f"macro {name} not defined")
        if name not in self.macro_use:
            self.macro_use.append(name)
        return f"__MACRO__{name}__"

    # -- keycodes ---------------------------------------------------------
    def key(self, tok: str) -> str:
        tok = tok.strip()
        if tok in JP_ALIASES:
            return self.key(JP_ALIASES[tok])
        m = re.fullmatch(r"(LS|LC|LA|LG)\((.*)\)", tok, re.S)
        if m:
            base, mods = split_expr(self.key(m.group(2)))
            return render(base, mods + [MODS[m.group(1)]])
        if tok in KEYS:
            base, mods = split_expr(KEYS[tok])
            return render(base, mods)
        self.unknown.add(tok)
        return f"UNKNOWN_{tok}"

    # -- bindings ---------------------------------------------------------
    def binding(self, b: list[str]) -> str:
        name, args = b[0], b[1:]
        if name == "kp":
            return self.key(args[0])
        if name == "trans":
            return "_"
        if name == "none":
            return "No"
        if name == "mt":                     # &mt MOD KEY
            return f"MT({self.key(args[1])}, {mods_of(self.key(args[0]))}, MT1)"
        if name == "lt":                     # &lt LAYER KEY
            return f"LT({args[0]}, {self.key(args[1])}, HT3)"
        if name == "mo":
            return f"MO({args[0]})"
        if name == "holdtap":                # bindings <hold>, <tap>
            return f"TH({self.key(args[1])}, {self.key(args[0])}, HT1)"
        if name == "imeonoff":
            return f"TH({self.key(args[1])}, {self.key(args[0])}, HT3)"
        if name == "lt_bsdel":               # <&mo>, <&BSDEL>
            return f"LT({args[0]}, Backspace, HT3)"
        if name == "mkp":
            return MOUSE[args[0]]
        if name == "mkp_layer":
            return f"LT({args[0]}, {MOUSE[args[1]]}, HT3)"
        if name == "out":                    # OUT_USB / OUT_BLE: RMK toggles output
            return "User8"
        if name == "bt":
            return "User7" if args[0] == "BT_CLR" else f"User{args[1]}"
        if name in ("ind_bat", "ind_con"):
            return "No"
        if name == "bootloader":
            return "Bootloader"
        if name == "slash":                  # mod-morph handled by a global fork
            return "Slash"
        if name in ("paren", "brack", "brace"):
            plain = {"paren": "parenthesis", "brack": "brackets", "brace": "braces"}[name]
            return f"TH({self.macro(plain)}, {self.macro('zen_' + plain)}, HT3)"
        if name.startswith("uj_"):
            return f"TH({self.macro(name[3:])}, {self.macro('jp_' + name[3:])}, HT2)"
        if name in MACROS:
            return self.macro(name)
        if name == "dblsft":
            return self.macro("DBLSFT")
        raise KeyError(f"unsupported behavior &{name}")


def split_expr(expr: str) -> tuple[str, list[str]]:
    if expr.startswith("SHIFTED(") and expr.endswith(")"):
        return expr[len("SHIFTED("):-1], ["LShift"]
    m = re.fullmatch(r"WM\(([^,]+), (.*)\)", expr)
    if m:
        return m.group(1), m.group(2).split("|")
    return expr, []


def render(base: str, mods: list[str]) -> str:
    uniq = [m for m in MOD_ORDER if m in mods]
    if not uniq:
        return base
    if uniq == ["LShift"]:
        return f"SHIFTED({base})"
    return f"WM({base}, {'|'.join(uniq)})"


MODIFIER_KEYS = {"LShift", "RShift", "LCtrl", "RCtrl", "LAlt", "RAlt", "LGui", "RGui"}


def mods_of(expr: str) -> str:
    """`&mt LCTRL TAB` passes the modifier as a plain keycode, not WM(...)."""
    base, mods = split_expr(expr)
    if not mods and base in MODIFIER_KEYS:
        return base
    uniq = [m for m in MOD_ORDER if m in mods]
    return "|".join(uniq) if uniq else "LShift"


# ---------------------------------------------------------------------------
# Combo / macro extraction
# ---------------------------------------------------------------------------
def read_combos():
    text = KEYMAP.read_text()
    block = re.search(r"combos \{(.*?)\n    \};", text, re.S).group(1)
    out = []
    for cm in re.finditer(r"(\w+) \{(.*?)\};", block, re.S):
        name, body = cm.group(1), cm.group(2)
        b = re.search(r"bindings = <(.*?)>;", body, re.S).group(1)
        pos = [int(x) for x in re.search(r"key-positions = <(.*?)>;", body).group(1).split()]
        lm = re.search(r"layers = <(.*?)>;", body)
        used = [int(x) for x in lm.group(1).split()] if lm else []
        binding = parse_bindings(b)[0]
        out.append((name, binding, pos, used))
    return out


HEADER = '''\
# moNa2 (PAW3222 trackball) -- RMK 0.9 configuration.
#
# GENERATED by tools/port_zmk_keymap.py from the ZMK config in
# ../zmk-for-moNa2-paw3222 (boards/shields/mona2/mona2.dtsi + config/mona2.keymap).
# Layout, layers, combos, hold-taps and the auto-mouse-layer follow the ZMK
# config; see README.md for the few places where RMK cannot be identical.
#
# Right half = split central (PAW3222 trackball), left half = split peripheral 0
# (EC11 encoder). Composite grid: cols 0..5 = left (6 col pins), cols 6..10 =
# right (5 col pins, col_offset = 6). (0,5) and (1,5) have no switch.

[keyboard]
name = "moNa2"
product_name = "moNa2 PAW3222"
vendor_id = 0x4c4b
product_id = 0x4e32
manufacturer = "razilyis"
chip = "nrf52840"

[layout]
rows = 4
cols = 11
map = """
(0,0,L) (0,1,L) (0,2,L) (0,3,L) (0,4,L) (0,5,L)                 (0,6,R) (0,7,R) (0,8,R) (0,9,R) (0,10,R)
(1,0,L) (1,1,L) (1,2,L) (1,3,L) (1,4,L) (1,5,L)                 (1,6,R) (1,7,R) (1,8,R) (1,9,R) (1,10,R)
(2,0,L) (2,1,L) (2,2,L) (2,3,L) (2,4,L) (2,5,L)                 (2,6,R) (2,7,R) (2,8,R) (2,9,R) (2,10,R)
(3,0,L) (3,1,L) (3,2,L) (3,3,L) (3,4,L) (3,5,L)                 (3,6,R) (3,7,R) (3,8,R) (3,9,R) (3,10,R)
"""

[ble]
enabled = true

[split]
connection = "ble"

# ---- right half: central ----
[split.central]
rows = 4
cols = 5
row_offset = 0
col_offset = 6
battery_adc_pin = "P0_31"
# XIAO nRF52840 VBAT divider: 1M + 510k
adc_divider_measured = 510
adc_divider_total = 1510

# XIAO VBAT measurement divider enable (P0_14, active low).
[[split.central.output]]
pin = "P0_14"
low_active = true
initial_state_active = true

[split.central.matrix]
matrix_type = "normal"
row_pins = ["P0_03", "P0_28", "P0_29", "P1_11"]
col_pins = ["P1_15", "P1_14", "P1_13", "P1_12", "P0_10"]

# ---- left half: peripheral 0 ----
[[split.peripheral]]
rows = 4
cols = 6
row_offset = 0
col_offset = 0
battery_adc_pin = "P0_31"
adc_divider_measured = 510
adc_divider_total = 1510

[[split.peripheral.output]]
pin = "P0_14"
low_active = true
initial_state_active = true

[split.peripheral.matrix]
matrix_type = "normal"
row_pins = ["P0_03", "P0_28", "P0_29", "P1_11"]
col_pins = ["P1_15", "P1_14", "P1_13", "P1_12", "P0_10", "P0_09"]

# Left-hand EC11 rotary encoder (A = D5/P0.05, B = D0/P0.02 on the XIAO).
[[split.peripheral.input_device.encoder]]
pin_a = "P0_05"
pin_b = "P0_02"
internal_pullup = true
phase = "resolution"
resolution = 2

[rmk]
split_peripherals_num = 1
ble_profiles_num = 5
# Put the keyboard to sleep after 10 minutes without key/pointer activity.
split_central_sleep_timeout_seconds = 600
# The ZMK config defines 18 combos.
combo_max_num = 32
combo_max_length = 3

[host]
vial_enabled = true
# Hold the two top-left keys together to unlock Vial configuration.
unlock_keys = [[0, 0], [0, 1]]

# The PAW3222 task in src/central.rs subscribes to layer events.
[event.layer_change]
subs = 2

# ---------------------------------------------------------------------------
# Hold-tap (morse) tuning, ported from the ZMK behaviors
# ---------------------------------------------------------------------------
# `&mt`          : tapping-term 200 ms (default), quick-tap 175 ms, tap-preferred
# `&holdtap`     : 300 ms, quick-tap 250 ms, require-prior-idle 150 ms
# `&lt`/`&paren`/`&uj_*`/`&imeonoff`/`&mkp_layer`: 200 ms
[behavior.morse]
hold_timeout = "200ms"
gap_timeout = "200ms"
# ZMK `&holdtap` uses require-prior-idle-ms = 150; RMK keeps that global.
prior_idle_time = "150ms"

[behavior.morse.profiles]
MT1 = { normal_mode = true, hold_timeout = "200ms", gap_timeout = "200ms", quick_tap_timeout = "175ms" }
HT1 = { normal_mode = true, hold_timeout = "300ms", gap_timeout = "250ms", quick_tap_timeout = "250ms" }
HT2 = { normal_mode = true, hold_timeout = "200ms", gap_timeout = "200ms" }
HT3 = { normal_mode = true, hold_timeout = "200ms", gap_timeout = "200ms" }

# ---------------------------------------------------------------------------
# Mod-morph replacements (RMK forks trigger on the keycode itself)
# ---------------------------------------------------------------------------
[behavior.fork]
forks = [
  # ZMK `slash`: Slash, or Backslash with Shift held
  { trigger = "Slash", negative_output = "Slash", positive_output = "WM(Backslash, LShift)", match_any = "LShift|RShift" },
  # ZMK `BSDEL`: Backspace, or Delete with Shift held (used by &lt_bsdel)
  { trigger = "Backspace", negative_output = "Backspace", positive_output = "Delete", match_any = "LShift|RShift" },
]

# ---------------------------------------------------------------------------
# Auto mouse layer (ZMK: zip_temp_layer 1 700, 500 ms timeout)
# ---------------------------------------------------------------------------
[[behavior.auto_mouse_layer]]
device_id = 0
target_layer = 1
timeout = "500ms"
threshold = 3
'''


LAYER_NAMES = ["Base", "Mouse", "Scroll", "Snipe", "Number", "Function", "System"]


def emit(transform, grids, combos, port, macro_names):
    parts = [HEADER]

    parts.append("\n[keymap]\nlayers = 7\n")
    for idx, name in enumerate(LAYER_NAMES):
        grid = grids[idx]
        rows = []
        for r in range(ROWS):
            rows.append(" ".join(grid[r][c] for c in range(COLS)))
        enc = ENCODERS[idx]
        parts.append(
            f'[[keymap.layer]]\nname = "{name}"\nkeys = """\n' + "\n".join(rows) +
            f'\n"""\nencoders = [["{enc[0]}", "{enc[1]}"]\n]\n'
        )

    # combos
    lines = []
    for name, binding, actions, layer in combos:
        act = ", ".join(f'"{a}"' for a in actions)
        extra = f", layer = {layer}" if layer is not None else ""
        lines.append(f'  {{ actions = [{act}], output = "{binding}"{extra} }},  # {name}')
    parts.append(
        '\n[behavior.combo]\ntimeout = "50ms"\nprior_idle_time = "130ms"\ncombos = [\n'
        + "\n".join(lines) + "\n]\n"
    )

    # macros
    for name in macro_names:
        ops = MACROS[name]
        body = ", ".join(f'{{ operation = "{op}", keycode = "{key}" }}' for op, key in ops)
        parts.append(f"[[behavior.macro.macros]]\noperations = [{body}]  # {name}\n")

    text = "".join(parts)
    for name in macro_names:
        text = text.replace(f"__MACRO__{name}__", f"MACRO({macro_names.index(name)})")
    return text


# Per-layer encoder actions, from the ZMK keymap's `sensor-bindings`
# (layer 0: C_VOLUME_DOWN/UP, NUMBER: LC(MINUS)/LC(PLUS),
#  FUNCTION: LC(PAGE_DOWN)/LC(PAGE_UP)).
ENCODERS = [
    ["AudioVolDown", "AudioVolUp"],
    ["AudioVolDown", "AudioVolUp"],           # Mouse layer: no ZMK binding, reuse base
    ["AudioVolDown", "AudioVolUp"],           # Scroll layer
    ["AudioVolDown", "AudioVolUp"],           # Snipe layer
    ["WM(Minus, LCtrl)", "WM(Equal, LShift)"],   # Number: LC(MINUS) / LC(PLUS)
    ["WM(PageDown, LCtrl)", "WM(PageUp, LCtrl)"],  # Function: LC(PAGE_DOWN) / LC(PAGE_UP)
    ["AudioVolDown", "AudioVolUp"],           # System layer
]


def main() -> None:
    transform = read_transform()
    layers = read_layers()
    port = Port()

    order = ["DEFAULT", "MOUSE", "SCROLL", "SNIPE", "NUMBER", "FUNCTION", "SYSTEM"]
    grids = []
    for name in order:
        bindings = layers[name]
        assert len(bindings) == len(transform), (name, len(bindings), len(transform))
        grid = [["No"] * COLS for _ in range(ROWS)]
        for (r, c), b in zip(transform, bindings):
            grid[r][c] = port.binding(b)
        grids.append(grid)

    combos = []
    for name, binding, positions, used in read_combos():
        layer_idx = 4 if used == [4] else 0
        acts = []
        for pos in positions:
            r, c = transform[pos]
            a = grids[layer_idx][r][c]
            if a in ("_", "No"):
                a = grids[0][r][c]
            acts.append(a)
        if any(a in ("_", "No") for a in acts):
            print(f"  !! combo {name}: unresolved actions {acts}")
        combos.append((name, port.binding(binding), acts, 4 if used == [4] else None))

    text = emit(transform, grids, combos, port, port.macro_use)
    OUT.write_text(text)
    print(f"wrote {OUT} ({len(text)} bytes)")
    print(f"  layers: {len(grids)}  combos: {len(combos)}  macros: {len(port.macro_use)}")
    if port.unknown:
        print(f"  !! unknown keycodes: {sorted(port.unknown)}")


if __name__ == "__main__":
    main()
