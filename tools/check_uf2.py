#!/usr/bin/env python3
"""Sanity-check UF2 images produced by tools/elf2uf2.py.

Fails loudly on the mistakes that silently produce an unbootable keyboard:
wrong block magic, wrong family id, or a base address that does not match
`FLASH ORIGIN` in memory.x (0x1000 on this board — app right after the MBR,
no SoftDevice).

Usage:  python3 tools/check_uf2.py [file.uf2 ...]     (default: moNa2-paw3222-*.uf2)
"""
from __future__ import annotations

import glob
import pathlib
import re
import struct
import sys

MAGIC_START0 = 0x0A324655
MAGIC_START1 = 0x9E5D5157
MAGIC_END = 0x0AB16F30
FAMILY_NRF52840 = 0xADA52840


def expected_base() -> int:
    """Read `FLASH ORIGIN` out of memory.x so this check cannot drift from the link."""
    memory_x = pathlib.Path(__file__).resolve().parents[1] / "memory.x"
    m = re.search(r"FLASH\s*:\s*ORIGIN\s*=\s*(0x[0-9A-Fa-f]+)", memory_x.read_text())
    if not m:
        raise SystemExit(f"{memory_x}: no FLASH ORIGIN found")
    return int(m.group(1), 16)


def check(path: str, app_base: int) -> tuple[int, int]:
    blob = open(path, "rb").read()
    if len(blob) % 512:
        raise SystemExit(f"{path}: size {len(blob)} is not a multiple of 512")

    expected_blocks = len(blob) // 512
    first = last = None
    for i in range(expected_blocks):
        block = blob[i * 512:(i + 1) * 512]
        m0, m1, _flags, addr, size, blk, total, fam = struct.unpack("<IIIIIIII", block[:32])
        end = struct.unpack("<I", block[508:512])[0]
        if (m0, m1) != (MAGIC_START0, MAGIC_START1):
            raise SystemExit(f"{path}: block {i} has bad start magic")
        if end != MAGIC_END:
            raise SystemExit(f"{path}: block {i} has bad end magic")
        if fam != FAMILY_NRF52840:
            raise SystemExit(f"{path}: block {i} family is {fam:#x}, expected {FAMILY_NRF52840:#x}")
        if blk != i or total != expected_blocks:
            raise SystemExit(f"{path}: block {i} numbering {blk}/{total} != {i}/{expected_blocks}")
        first = addr if first is None else first
        last = addr
    if first != app_base:
        raise SystemExit(
            f"{path}: first block targets {first:#010x}, expected {app_base:#010x} (memory.x FLASH ORIGIN)"
        )
    if last < first:
        raise SystemExit(f"{path}: last block address {last:#010x} is below the first")
    return expected_blocks, first


def main() -> None:
    paths = sys.argv[1:] or sorted(glob.glob("moNa2-paw3222-*.uf2"))
    if not paths:
        raise SystemExit("no UF2 files given and none matched moNa2-paw3222-*.uf2")
    app_base = expected_base()
    for p in paths:
        blocks, base = check(p, app_base)
        print(f"{p}: OK, {blocks} blocks, base {base:#010x} (memory.x), family {FAMILY_NRF52840:#x}")


if __name__ == "__main__":
    main()
