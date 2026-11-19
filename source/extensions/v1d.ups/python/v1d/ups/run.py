# SPDX-License-Identifier: MIT
"""Subprocess upscale-frame wrapper (worker thread safe)."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from .png_io import read_rgba_png, write_rgba_png
except ImportError:
    from png_io import read_rgba_png, write_rgba_png

ENGINE_IDS = ("seedvr2", "flashvsr", "realesrgan", "realcugan", "video2x", "rve", "fake")

DEFAULT_SCALE = 4


@dataclass
class UpscaleResult:
    ok: bool
    wall_s: float
    out_w: int = 0
    out_h: int = 0
    rgba: bytes = b""
    error: str = ""


def _fake_upscale(in_path: str, out_path: str, scale: int = DEFAULT_SCALE) -> None:
    w, h, rgba = read_rgba_png(in_path)
    ow, oh = w * scale, h * scale
    out = bytearray(ow * oh * 4)
    for y in range(oh):
        sy = y // scale
        for x in range(ow):
            sx = x // scale
            si = (sy * w + sx) * 4
            oi = (y * ow + x) * 4
            out[oi : oi + 4] = rgba[si : si + 4]
    write_rgba_png(out_path, ow, oh, bytes(out))


def upscale_png(
    root: str,
    engine_id: str,
    input_png: str,
    output_png: str,
    timeout_s: float = 600.0,
) -> UpscaleResult:
    t0 = time.perf_counter()
    engine_id = engine_id.strip().lower()
    if engine_id not in ENGINE_IDS:
        return UpscaleResult(False, 0.0, error=f"unknown engine: {engine_id}")

    exe = Path(root) / "bin" / "upscale-frame"
    try:
        if engine_id == "fake" or not exe.is_file():
            _fake_upscale(input_png, output_png)
        else:
            proc = subprocess.run(
                [str(exe), "--engine", engine_id, "--input", input_png, "--output", output_png],
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "upscale failed").strip()[:500]
                return UpscaleResult(False, time.perf_counter() - t0, error=err)
        w, h, rgba = read_rgba_png(output_png)
        return UpscaleResult(True, time.perf_counter() - t0, out_w=w, out_h=h, rgba=rgba)
    except subprocess.TimeoutExpired:
        return UpscaleResult(False, time.perf_counter() - t0, error="timeout")
    except OSError as exc:
        return UpscaleResult(False, time.perf_counter() - t0, error=str(exc))


def upscale_png_bytes(
    root: str,
    engine_id: str,
    width: int,
    height: int,
    rgba: bytes,
    stride: int,
    work_dir: str,
    timeout_s: float = 600.0,
) -> UpscaleResult:
    os.makedirs(work_dir, exist_ok=True)
    in_png = os.path.join(work_dir, "in.png")
    out_png = os.path.join(work_dir, "out.png")
    write_rgba_png(in_png, width, height, rgba, stride)
    return upscale_png(root, engine_id, in_png, out_png, timeout_s=timeout_s)
