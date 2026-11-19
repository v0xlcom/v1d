# SPDX-License-Identifier: MIT
"""Shared barcode helpers for C4 exact-decode tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def fixture_meta(fixtures: Path, name: str) -> dict:
    meta = json.loads((fixtures / f"{name}.expected.json").read_text())
    return meta


def rgba_at(pixels: bytes, stride: int, x: int, y: int) -> tuple[int, int, int, int]:
    off = y * stride + x * 4
    return pixels[off], pixels[off + 1], pixels[off + 2], pixels[off + 3]


def barcode_from_rgba_proxy(pixels: bytes, stride: int, meta: dict, out_w: int, out_h: int) -> int:
    """C12: map source block centers into proxy RGBA space."""
    src_w = int(meta["width"])
    src_h = int(meta["height"])
    block_w = meta["block_w"]
    block_h = meta["block_h"]
    cy_src = block_h // 2
    value = 0
    for i in range(32):
        cx_src = i * block_w + block_w // 2
        cx = min(out_w - 1, max(0, int(cx_src * out_w / src_w)))
        cy = min(out_h - 1, max(0, int(cy_src * out_h / src_h)))
        r, g, b, _ = rgba_at(pixels, stride, cx, cy)
        if r > 128 and g > 128 and b > 128:
            value |= 1 << (31 - i)
    return value


def barcode_from_rgba(pixels: bytes, stride: int, meta: dict) -> int:
    block_w = meta["block_w"]
    block_h = meta["block_h"]
    cy = block_h // 2
    value = 0
    for i in range(32):
        cx = i * block_w + block_w // 2
        r, g, b, _ = rgba_at(pixels, stride, cx, cy)
        if r > 128 and g > 128 and b > 128:
            value |= 1 << (31 - i)
    return value


def sync_indices(mp4: Path) -> list[int]:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_packets",
            "-show_entries",
            "packet=pts_time,flags",
            "-of",
            "csv=p=0",
            str(mp4),
        ],
        text=True,
    )
    indices: list[int] = []
    for i, line in enumerate(out.strip().splitlines()):
        if "K" in line.split(",")[-1]:
            indices.append(i)
    return indices


def c4_target_indices(n: int, mp4: Path, is_4k: bool) -> list[int]:
    import random

    targets = {0, 1, 2, max(0, n - 3), max(0, n - 2), max(0, n - 1)}
    syncs = sync_indices(mp4)
    for s in syncs[:20]:
        for d in (-1, 0, 1):
            targets.add(max(0, min(n - 1, s + d)))
    rng = random.Random(0)
    random_n = 100 if is_4k else 300
    for _ in range(random_n):
        targets.add(rng.randrange(n))
    return sorted(targets)
