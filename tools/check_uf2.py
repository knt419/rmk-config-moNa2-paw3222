#!/usr/bin/env python3
"""Sanity-check UF2 images produced by tools/elf2uf2.py.

Fails loudly on the mistakes that silently produce an unbootable keyboard:
wrong block magic, wrong family id, or a base address that does not match the
application partition (0x26000 on this board).

Usage:  python3 tools/check_uf2.py [file.uf2 ...]     (default: moNa2-paw3222-*.uf2)
"""
from __future__ import annotations

import glob
import struct
import sys

MAGIC_START0 = 0x0A324655
MAGIC_START1 = 0x9E5D5157
MAGIC_END = 0x0AB16F30
FAMILY_NRF52840 = 0xADA52840
APP_BASE = 0x00026000


def check(path: str) -> tuple[int, int]:
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
    if first != APP_BASE:
        raise SystemExit(f"{path}: first block targets {first:#010x}, expected {APP_BASE:#010x}")
    if last < first:
        raise SystemExit(f"{path}: last block address {last:#010x} is below the first")
    return expected_blocks, first


def main() -> None:
    paths = sys.argv[1:] or sorted(glob.glob("moNa2-paw3222-*.uf2"))
    if not paths:
        raise SystemExit("no UF2 files given and none matched moNa2-paw3222-*.uf2")
    for p in paths:
        blocks, base = check(p)
        print(f"{p}: OK, {blocks} blocks, base {base:#010x}, family {FAMILY_NRF52840:#x}")


if __name__ == "__main__":
    main()
