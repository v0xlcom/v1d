# SPDX-License-Identifier: MIT
"""Minimal RGBA8 PNG read/write (stdlib only)."""

from __future__ import annotations

import struct
import zlib


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag)
    crc = zlib.crc32(data, crc) & 0xffffffff
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


def read_rgba_png(path: str) -> tuple[int, int, bytes]:
    with open(path, "rb") as f:
        sig = f.read(8)
        if sig != b"\x89PNG\r\n\x1a\n":
            raise ValueError("not a PNG")
        width = height = 0
        idat = bytearray()
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            length, tag = struct.unpack(">I4s", hdr)
            data = f.read(length)
            f.read(4)
            if tag == b"IHDR":
                width, height = struct.unpack(">II", data[:8])
            elif tag == b"IDAT":
                idat.extend(data)
            elif tag == b"IEND":
                break
        if width <= 0 or height <= 0:
            raise ValueError("bad IHDR")
        raw = zlib.decompress(bytes(idat))
        stride = width * 4
        rgba = bytearray(height * stride)
        pos = 0
        for y in range(height):
            pos += 1
            rgba[y * stride : (y + 1) * stride] = raw[pos : pos + stride]
            pos += stride
        return width, height, bytes(rgba)
