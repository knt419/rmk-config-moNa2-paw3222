# rmk-config-moNa2-paw3222

RMK 0.9 firmware for **moNa2** (the PAW3222 trackball variant), ported from the
ZMK config in [`knt419/zmk-for-moNa2-paw3222`](https://github.com/knt419/zmk-for-moNa2-paw3222).

* **Right half** — split **central**: XIAO nRF52840 + PAW3222 trackball, connects to the host over BLE (or USB when plugged in).
* **Left half** — split **peripheral 0**: XIAO nRF52840 + EC11 rotary encoder.
* Keymap, layers, combos, hold-taps and the auto-mouse-layer follow the ZMK config; `keyboard.toml` is generated from it (see [`tools/`](#tools)).

| | |
|---|---|
| Firmware | RMK 0.9.0 (`rmk = "0.9"`), embassy async, no RTOS |
| MCU | nRF52840 (Seeed XIAO nRF52840), SoftDevice Controller via `nrf-sdc` |
| Split | BLE, 1 peripheral |
| Flash | `0x26000`, 872 K — application partition behind the UF2 bootloader |
| Sizes (release) | central `text 466 K`, peripheral `text 283 K` |
| Status | builds clean; **not yet tested on hardware** (see [Bring-up](#bring-up-checklist)) |

---

## Build

Prerequisites on Arch/Omarchy:

```bash
rustup target add thumbv7em-none-eabihf
rustup component add llvm-tools
cargo install flip-link

# nrf-mpsl-sys / nrf-sdc-sys compile MPSL's C sources, so an ARM C toolchain is
# required. The Arm GNU toolchain (with newlib headers) works; a bare clang
# fails on <string.h>.
curl -LO https://developer.arm.com/-/media/Files/downloads/gnu/13.3.rel1/binrel/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi.tar.xz
tar -xf arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi.tar.xz -C ~/.local
export PATH="$HOME/.local/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi/bin:$PATH"
```

Build both halves:

```bash
cargo build --release              # or: --bin central / --bin peripheral
```

Flashable images:

```bash
python3 tools/elf2uf2.py target/thumbv7em-none-eabihf/release/central    moNa2-paw3222-central.uf2
python3 tools/elf2uf2.py target/thumbv7em-none-eabihf/release/peripheral moNa2-paw3222-peripheral.uf2
```

Double-tap reset on each XIAO (or hold the `Bootloader` key on the System layer),
then copy the matching `.uf2` to the mounted drive: `central` → **right** half,
`peripheral` → **left** half. With a debug probe, `cargo run --release --bin central`
works too (`.cargo/config.toml` sets `probe-rs run --chip nRF52840_xxAA`).

Debug logging goes over RTT (`DEFMT_LOG=info` in `.cargo/config.toml`), so
`probe-rs attach` / `defmt-print` is needed to see it.

## Edit the keymap

The keymap is **generated**, so the ZMK config stays the single source of truth:

```bash
python3 tools/port_zmk_keymap.py     # ZMK keymap -> keyboard.toml (7 layers, 18 combos, 25 macros)
python3 tools/gen_vial_json.py       # vial.json (Vial keyboard definition)
python3 tools/check_keycodes.py      # validate every keycode against RMK's enums
cargo build --release
```

Hand-editing `keyboard.toml` works, but the next porter run overwrites the keymap
sections. Runtime remapping is possible through **Vial** (`vial_enabled = true`;
hold top-left `Q`+`W` to unlock).

## Hardware map

| Function | Pin | Notes |
|---|---|---|
| Matrix rows (both halves) | `P0_03`, `P0_28`, `P0_29`, `P1_11` | `row2col = false` (col2row) |
| Left columns (6) | `P1_15`, `P1_14`, `P1_13`, `P1_12`, `P0_10`, `P0_09` | cols 0–5 of the composite grid |
| Right columns (5) | `P1_15`, `P1_14`, `P1_13`, `P1_12`, `P0_10` | cols 6–10 (`col_offset = 6`) |
| Trackball SCLK | `P0_05` (D5) | bit-banged 3-wire SPI (`rmk::driver::bitbang_spi`) |
| Trackball SDIO | `P0_04` (D4) | bidirectional; switched to input with `Pull::None` |
| Trackball CS | `P0_09` | |
| Trackball MOTION | `P0_02` (D0) | active low, `Pull::Up` |
| Encoder A / B | `P0_05` / `P0_02` | left half only, internal pull-ups |
| Battery ADC | `P0_31`, divider 510/1510 | both halves; `P0_14` driven low to enable the divider |

The composite keymap grid is 4 × 11 = 44 slots, but only 42 switches exist:
`(0,5)` and `(1,5)` are unpopulated and are kept as `No` so grid indices stay
aligned with the layout map that Vial uses.

## How the trackball is wired into RMK

`src/paw3222.rs` implements RMK's `PointingDriver` for the PAW3222 (register
sequence ported from `sekigon-gonnoc/zmk-driver-paw3222`, which is what the ZMK
build runs: product-ID probe → reset → `WRITE_PROTECT` unlock → CPI → sleep mode
→ 8-bit signed `DELTA_X`/`DELTA_Y`).

`src/central.rs` then uses the stock `PointingDevice` + `PointingProcessor`, and
overrides the generated entry point with `#[Overwritten(entry)]` because the
stock pointing processor needs `&keymap`, which only exists inside `main()`.
Everything the generated block used to spawn (transports, battery ADC, auto
mouse layer) is spawned there explicitly. Pointing modes are driven from layer
changes: layer **2 = scroll** (one notch per 144 counts), layer **3 = sniper**
(1/4), otherwise cursor. `[[behavior.auto_mouse_layer]]` activates layer 1 on
ball motion (500 ms timeout).

CPI defaults to `2280` (60 counts/inch, `DEFAULT_CPI` in `src/paw3222.rs`); it
must be a multiple of 38 within 608…4826. Lower CPI means fewer HID reports per
inch of ball travel, which matters more on a wireless link than raw sensitivity —
raise the divisor/scaler instead of the CPI if the cursor feels slow.

## Ported from the ZMK config

| ZMK | RMK |
|---|---|
| 7 layers: `DEFAULT, MOUSE, SCROLL, SNIPE, NUMBER, FUNCTION, SYSTEM` | 7 layers, same positions (`tools/port_zmk_keymap.py` maps transform order → matrix grid) |
| `&mt` (quick-tap 175 ms, tap-preferred) | `MT(key, mod, MT1)` |
| `&holdtap` (300 ms, quick-tap 250, prior-idle 150) | `TH(tap, hold, HT1)` |
| `&lt`, `&paren`, `&brack`, `&brace`, `&imeonoff`, `&mkp_layer`, `&uj_*` (200 ms) | `LT(..., HT3)`, `TH(..., HT2/HT3)` |
| 18 `combos {}` entries | `[behavior.combo]` |
| `zip_temp_layer 1 700` auto mouse layer | `[[behavior.auto_mouse_layer]]` (layer 1) |
| `scroller { layers = <2>; }` / `sniper { layers = <3>; }` | `PointingMode::Scroll` / `Sniper` on layers 2 / 3 |
| `&slash`, `BSDEL` mod-morphs | `[behavior.fork]` on `Slash` / `Backspace` |
| JP symbol macros (`&at`, `&paren`, `uj_*`, `zen_*`, …) | `[[behavior.macro.macros]]` + `MACRO(n)` |
| `sensor-bindings` per layer | `encoders = [[cw, ccw]]` per layer |

### Known differences from ZMK

These are RMK constraints, not porting bugs — check them before flashing:

* **Combos match keycodes, not positions.** RMK triggers a combo on the *resolved
  action* at the pressed keys, so a combo listed as `["S", "TH(A, WM(A, LCtrl), HT1)"]`
  fires wherever those actions appear. ZMK's per-combo `timeout-ms` /
  `require-prior-idle-ms` collapse into the global `timeout = 50ms` /
  `prior_idle_time = 130ms`.
* **Auto mouse layer threshold is per-event**, not accumulated pixels (ZMK's `700`).
  It is set to `3` counts; raise it if the layer triggers too eagerly.
* **`&out OUT_USB` / `&out OUT_BLE` both map to `User8`**, which *toggles* the
  output in RMK rather than selecting an absolute one.
* **`&lt_bsdel`** becomes `LT(5, Backspace)`; the Shift→Delete morph is applied by
  the global `Backspace` fork.
* **`&ind_bat` / `&ind_con`** (RGB/battery indicators) have no RMK equivalent and
  are `No`. There is no RGB support in RMK 0.9, so the `rgbled_adapter` widget from
  the ZMK build is not reproduced.
* **`&holdtap` flavors**: ZMK's `tap-preferred` + `hold-trigger-on-release` is
  approximated by RMK's `normal_mode` (time-based) profiles.
* **`winmvright`/`winmvleft` macros** are simplified to `Gui+Right` / `Gui+Left`
  press-tap-release (ZMK's version re-taps keys as a workaround).
* **Vial layout** lists all 44 slots including the two unpopulated ones, so keys
  appear at their matrix positions rather than on a prettified physical layout.
* `[rmk].ble_profiles_num = 5` matches the ZMK profile count; RMK's `User0..User4`
  select profiles, `User5/6` cycle, `User7` clears the bond, `User8` toggles output.

## Layout of the repo

```
keyboard.toml        generated: hardware, 7 layers, combos, macros, forks, morse profiles
vial.json            generated: Vial keyboard definition (44 matrix positions)
src/central.rs       right half: trackball + transports + split central entry override
src/peripheral.rs    left half (matrix/encoder/battery come from keyboard.toml)
src/paw3222.rs       PAW3222 driver + RMK PointingDriver impl
memory.x             FLASH 0x26000/872K, RAM 0x20000000/256K
tools/port_zmk_keymap.py   ZMK .keymap + .dtsi  ->  keyboard.toml
tools/gen_vial_json.py     -> vial.json
tools/check_keycodes.py    validates keycodes against rmk-types enums
tools/elf2uf2.py           ELF -> UF2 (family 0xADA52840)
```

## Bring-up checklist

Nothing here has run on hardware yet. In order:

1. Flash **central** first, watch RTT: expect `PAW3222 detected (product id 0x30)`.
   If the product ID is wrong or reads fail, the bit-bang transport / wiring is at
   fault — do not touch CPI or transforms yet.
2. Move the ball: cursor motion over **USB** (plug the right half in) with the
   buttons, scroll layer (2) and sniper layer (3) behaving as expected.
3. Flash the **left** half, confirm the halves pair (BLE split pairing is
   automatic on first boot; a stale bond needs `User7`).
4. Check the encoder on both a base-layer and Number-layer detent.
5. Then compare BLE cursor smoothness against the ZMK build, and only then tune
   `DEFAULT_CPI`, `SCROLL_DIVISOR` in `src/central.rs`, or the auto-mouse threshold.
