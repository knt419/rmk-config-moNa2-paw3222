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
| Flash | `0x1000`, 1020 K — application right after the protected MBR (no SoftDevice) |
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

## Troubleshooting

**Flashed, but nothing happens at all** — no USB device, no BLE advertisement, neither
half types. Check the link address before anything else:

```bash
arm-none-eabi-readelf -lW target/thumbv7em-none-eabihf/release/central | grep LOAD
python3 tools/check_uf2.py          # must agree with memory.x
```

The first LOAD segment has to be at `0x00001000`. This board's UF2 bootloader carries
**no SoftDevice**, so the application starts right after the 4 KB MBR. An image linked
at `0x26000` — the *SoftDevice* partition layout ZMK uses
(`nordic/nrf52840_partition_uf2_sdv7.dtsi`, where the SoftDevice occupies
`0x1000..0x26000`) — flashes without any error and then never boots, because the
bootloader jumps to `0x1000` and finds nothing. An earlier revision of this repo made
exactly that mistake; `memory.x` now documents it inline, and `tools/elf2uf2.py` takes
the UF2 base from the ELF's load address while `tools/check_uf2.py` cross-checks it
against `memory.x`, so the two cannot drift again.

**Cursor moves the wrong way.** Flip `INVERT_X` / `INVERT_Y` at the top of
`src/paw3222.rs`. The ZMK overlay for this board carries `invert-x; invert-y;`, but with
both applied the RMK build moved the cursor backwards on hardware, so they default to
`false`. Change only the axis that is wrong: `INVERT_X` for left/right, `INVERT_Y` for
up/down (scroll mode uses the same signs).

**Keys on the left half are dropped.** The left half is the BLE split peripheral, so a
missing key is a lost split event, not a matrix fault — the right half typing fine proves
the keymap and the central. Two known causes:

- `[rmk] split_central_sleep_timeout_seconds` in `keyboard.toml`: with a non-zero value
  RMK slows the peripheral link while idle, and the first key after a pause is lost. It is
  `0` (disabled) by default here, which matches the known-good config; raise it to e.g.
  `600` for battery life only once the link is trusted.
- Stale bonds in flash from an earlier firmware: RMK's storage layout is not stable across
  versions, so the central can be left holding a peer address / keys that no longer match.
  Flash a `clear_storage` build once on **both** halves, then reflash the normal build and
  re-pair the host:

  ```bash
  printf '\n[storage]\nenabled = true\nclear_storage = true\n' >> keyboard.toml
  cargo build --release --bins
  # flash both halves, restore keyboard.toml, rebuild, flash again
  ```

  `moNa2-paw3222-{central,peripheral}-storage-reset.uf2` are exactly that build.

**Keys work but the trackball does nothing.** Build the bisect image below to prove the
keyboard path, then attach RTT (`probe-rs attach --chip nRF52840_xxAA`) and look for
`PAW3222 detected (product id 0x30)`. If the product ID is wrong or the reads fail, the
bit-banged SDIO transport is at fault — not CPI, not the transforms.

**Left half types nothing, right half is fine.** That is the split link, not the matrix:
check that both halves run the same build, clear the stored peer bond (`User7` on the
System layer) and power-cycle both.

### Bisect build: no trackball

`--no-default-features` drops the `trackball` feature: `src/paw3222.rs` is not compiled
and the `#[Overwritten(entry)]` override is replaced by RMK's stock generated entry
point.

```bash
cargo build --release --bin central --no-default-features
python3 tools/elf2uf2.py target/thumbv7em-none-eabihf/release/central central-notrackball.uf2
```

If keys work there but not in the default build, the fault is in the sensor wiring or
the entry override — not in the matrix, the split config or the keymap.

## Continuous integration

`.github/workflows/build.yml` runs on pushes to `main`, on pull requests, on
`workflow_dispatch`, and on `v*` tags:

1. **Keycode validation** — `tools/check_keycodes.py` checks every action in
   `keyboard.toml` against RMK's keycode enums. In a plain build the config parser
   reports one unknown key per run, through a macro panic whose headline message is
   empty, so this validates the whole file up front.
2. **Vial drift check** — regenerates `vial.json` and fails if it differs from the
   committed one.
3. **Build both roles** — `cargo build --release --bins`. Split-peripheral and
   central-only config sections are validated per binary, so both have to build.
   Warnings are errors via `[lints.rust] warnings = "deny"` in `Cargo.toml`;
   `RUSTFLAGS=-D warnings` is deliberately *not* used, because it would also deny
   warnings coming from `rmk`/`embassy`.
4. **Size report** — `arm-none-eabi-size` for both binaries, written to the job
   summary next to the 1020 K partition budget.
5. **UF2 packaging** — `tools/elf2uf2.py`, then `tools/check_uf2.py` asserts block
   magic, family `0xADA52840`, block numbering and the address `FLASH ORIGIN` in `memory.x`.
6. **Artifacts** — `central`/`peripheral` `.uf2` plus the matching `.elf`, uploaded as
   `rmk-moNa2-paw3222-<ref>-<sha7>`.

Pushing a `v*` tag additionally attaches both `.uf2` files to a GitHub Release.

Each step was reproduced locally (see the commit message for the sizes and UF2
checks); the workflow file itself has only been validated with `actionlint`.

## Edit the keymap

The keymap is **generated**, so the ZMK config stays the single source of truth:

```bash
python3 tools/port_zmk_keymap.py     # ZMK keymap -> keyboard.toml (7 layers, 18 combos, 25 macros)
python3 tools/gen_vial_json.py       # vial.json (Vial keyboard definition)
python3 tools/keymap_diagram.py      # redraw the "Default keymap" diagrams below
python3 tools/check_keycodes.py      # validate every keycode against RMK's enums
cargo build --release
```

`port_zmk_keymap.py` and `keymap_diagram.py` read the sibling checkout at
`~/Projects/zmk-for-moNa2-paw3222` (path at the top of each script); the other two are
self-contained.

Hand-editing `keyboard.toml` works, but the next porter run overwrites the keymap
sections. Runtime remapping is possible through **Vial** (`vial_enabled = true`;
hold top-left `Q`+`W` to unlock).

## Default keymap

Port of the ZMK keymap (7 layers). Layer 2 is the scroll layer and layer 3 the sniper
layer for the ball; layer 1 is the auto-mouse layer that engages on ball motion.

<!-- keymap-diagram:start -->
Generated by `tools/keymap_diagram.py` from `keyboard.toml`; positions come from the ZMK physical layout in `mona2.dtsi`.

`_` transparent · `·` no key · `tap/hold` = tap on tap, hold on hold · `key/N` = layer-tap to layer *N* · `key^` = key+Ctrl, `keyS` = key+Shift, `keyG` = key+Gui, `keyA` = key+Alt · the left block is the left half (6 columns), the right block is the right half; its leftmost column is the inner thumb column (populated on the middle rows only).

**Base**

```
   Q        R        -        G        Z                            /        C/C^     H        L        Y
   U        N        I        T        D                   Esc/6    P        O        K        A/A^     S
   V/S      ,/!      ./?      M        W        Caps       ;        X/X^     E/EG     B        F        J
   M^S/Spc^ PgU^/G   PgD^/A   LClk     Spc/S    Tab/^      BkSp/5   Ent/4                               PrtS
```

**Mouse**

```
   _        _        _        _        _                            _        _        _        _        _
   _        _        _        _        _                   _        _        _        _        _        _
   _        _        _        _        _        _          _        _        LClk     MClk/2   RClk     _
   _        _        _        _        MClk/2   RClk/3     _        _                                   _
```

**Scroll**

```
   _        _        _        _        _                            _        _        _        _        _
   _        _        _        _        _                   _        _        _        _        _        _
   _        _        _        _        _        _          _        _        _        _        _        _
   _        _        _        _        _        _          _        _                                   _
```

**Snipe**

```
   _        _        _        _        _                            _        _        _        _        _
   _        _        _        _        _                   _        _        _        _        _        _
   _        _        _        _        _        _          _        _        _        _        _        _
   _        _        _        _        _        _          _        _                                   _
```

**Number**

```
   */"      Kc7      Kc8      Kc9      +/:                          ~/+      M0/M1    M2/M3    M4/M5    M6/M7
   //%      Kc4      Kc5      Kc6      -                   _        Left     Down     Up       Rght     \
   Kc0      Kc1      Kc2      Kc3      :/'      NumL       M8/M9    !        M10/M11  M12      M13/M14  M15
   %        ,        .        RClk     =/S      ./^        _        _                                   _/I1S
```

**Function**

```
   {/}      F7       F8       F9       F12                          Ins      Del      PrtS     Paus     }/|
   (/*      F4       F5       F6       F11                 _        Home     PgD      PgU      End      )/(
   [/]      F1       F2       F3       F10      ScrL^A     Esc^S    MPrev    MPlay    MStop    MNext    ]/\
   LeftA    RghtA    R^       MClk     Z^/S     Y^/^       _        _                                   Menu
```

**System**

```
   ·        _        _        ·        U8                           U8       ·        _        _        ·
   _        U3       U4       _        _                   _        U0       U1       U2       U3       U4
   _        U0       U1       U2       U8       U7         _        U8       _        _        _        _
   Boot     _        _        _        _        _          _        _                                   Boot
```

<!-- keymap-diagram:end -->

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
memory.x             FLASH 0x1000/1020K, RAM 0x20000008/255K
.github/workflows/build.yml  CI: validate -> build both bins -> UF2 -> artifacts (release on v* tags)
tools/port_zmk_keymap.py   ZMK .keymap + .dtsi  ->  keyboard.toml
tools/gen_vial_json.py     -> vial.json
tools/check_keycodes.py    validates keycodes against rmk-types enums
tools/elf2uf2.py           ELF -> UF2 (family 0xADA52840)
tools/check_uf2.py         validates UF2 magic / family / block numbering / base
tools/keymap_diagram.py    renders the default keymap diagrams into this README
```

## Bring-up checklist

Nothing here has run on hardware yet. In order:

1. Confirm the image links at `0x1000` (`readelf -lW ... | grep LOAD`) before flashing
   anything — a wrong origin looks like "dead keyboard", not like a bad flash.
2. Flash **central** first, watch RTT: expect `PAW3222 detected (product id 0x30)`.
   If the product ID is wrong or reads fail, the bit-bang transport / wiring is at
   fault — do not touch CPI or transforms yet. If nothing at all appears, flash the
   `--no-default-features` build to rule the sensor path out.
3. Move the ball: cursor motion over **USB** (plug the right half in) with the
   buttons, scroll layer (2) and sniper layer (3) behaving as expected.
4. Flash the **left** half, confirm the halves pair (BLE split pairing is
   automatic on first boot; a stale bond needs `User7`).
5. Check the encoder on both a base-layer and Number-layer detent.
6. Then compare BLE cursor smoothness against the ZMK build, and only then tune
   `DEFAULT_CPI`, `SCROLL_DIVISOR` in `src/central.rs`, or the auto-mouse threshold.
