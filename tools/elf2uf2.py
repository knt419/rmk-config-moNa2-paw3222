#!/usr/bin/env python3
"""Convert an RMK ELF into a UF2 image for the XIAO nRF52840 bootloader.

Avoids needing `cargo-hex-to-uf2`: it runs arm-none-eabi-objcopy to get a raw
binary and then packs standard UF2 blocks (512 bytes, 256-byte payloads, family
0xADA52840). Addresses come straight from the ELF, which is linked at 0x26000.

Usage:  python3 tools/elf2uf2.py <elf> <out.uf2>
"""
from __future__ import annotations

import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile

UF2_MAGIC_START0 = 0x0A324655
UF2_MAGIC_START1 = 0x9E5D5157
UF2_MAGIC_END = 0x0AB16F30
UF2_FLAG_FAMILY_ID_PRESENT = 0x00002000
FAMILY_NRF52840 = 0xADA52840
PAYLOAD = 256


def objcopy_bin(elf: pathlib.Path, out: pathlib.Path) -> None:
    objcopy = shutil.which("arm-none-eabi-objcopy") or shutil.which("llvm-objcopy")
    if not objcopy:
        raise SystemExit("arm-none-eabi-objcopy / llvm-objcopy not found on PATH")
    subprocess.run([objcopy, "-O", "binary", str(elf), str(out)], check=True)


def load_base(elf: pathlib.Path) -> int:
    """Lowest LOAD-segment physical address, i.e. where the image must be written.

    Derived from the ELF instead of a constant: the flash origin lives in
    `memory.x`, and a UF2 written to the wrong base flashes silently and never
    boots.
    """
    readelf = shutil.which("arm-none-eabi-readelf") or shutil.which("llvm-readelf")
    if not readelf:
        raise SystemExit("arm-none-eabi-readelf / llvm-readelf not found on PATH")
    text = subprocess.run([readelf, "-l", str(elf)], check=True, capture_output=True, text=True).stdout
    addrs = [
        int(m.group(1), 16)
        for m in (
            re.match(r"\s*LOAD\s+0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+\s+(0x[0-9a-fA-F]+)", line)
            for line in text.splitlines()
        )
        if m
    ]
    if not addrs:
        raise SystemExit(f"{elf}: no LOAD segments found")
    return min(addrs)


def make_uf2(blob: bytes, base: int, out: pathlib.Path) -> int:
    blocks = (len(blob) + PAYLOAD - 1) // PAYLOAD
    with out.open("wb") as fh:
        for i in range(blocks):
            chunk = blob[i * PAYLOAD:(i + 1) * PAYLOAD]
            chunk = chunk + b"\x00" * (PAYLOAD - len(chunk))
            header = struct.pack(
                "<IIIIIIII",
                UF2_MAGIC_START0,
                UF2_MAGIC_START1,
                UF2_FLAG_FAMILY_ID_PRESENT,
                base + i * PAYLOAD,
                PAYLOAD,
                i,
                blocks,
                FAMILY_NRF52840,
            )
            fh.write(header)
            fh.write(chunk)
            fh.write(b"\x00" * (476 - PAYLOAD))
            fh.write(struct.pack("<I", UF2_MAGIC_END))
    return blocks


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    elf = pathlib.Path(sys.argv[1])
    out = pathlib.Path(sys.argv[2])

    with tempfile.TemporaryDirectory() as tmp:
        raw = pathlib.Path(tmp) / "app.bin"
        objcopy_bin(elf, raw)
        blob = raw.read_bytes()

    base = load_base(elf)
    n = make_uf2(blob, base, out)
    print(f"{out}: {n} blocks, {len(blob)} bytes, base {base:#010x} (from ELF load address)")


if __name__ == "__main__":
    main()
