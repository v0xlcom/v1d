# SPDX-License-Identifier: MIT
"""Minimal RGBA8 PNG write (stdlib only)."""

from __future__ import annotations

import struct
import zlib


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def write_rgba_png(path: str, width: int, height: int, rgba: bytes, stride: int | None = None) -> None:
    if stride is None:
        stride = width * 4
    row_bytes = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        off = y * stride
        raw.extend(rgba[off : off + row_bytes])
    compressed = zlib.compress(bytes(raw), 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    out = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", compressed)
    out += _png_chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(out)