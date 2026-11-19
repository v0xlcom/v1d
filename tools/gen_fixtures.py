#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate barcode/color-patch MP4 fixtures (dev only; uses system ffmpeg)."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FRAME_LABEL_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
OUT = ROOT / "tests" / "fixtures"

PATCH_RGBA = [
    (0, 0, 0, 255),
    (255, 255, 255, 255),
    (255, 0, 0, 255),
    (0, 255, 0, 255),
    (0, 0, 255, 255),
    (255, 255, 0, 255),
    (0, 255, 255, 255),
    (255, 0, 255, 255),
]


@dataclass(frozen=True)
class Spec:
    name: str
    codec: str  # h264 | hevc
    width: int
    height: int
    fps_num: int
    fps_den: int
    gop: int
    bframes: int
    depth: int
    seconds: int
    open_gop: bool = False
    aac_beep: bool = False


SPECS = [
    Spec("h264_1080_g30_b2", "h264", 1920, 1080, 30, 1, 30, 2, 8, 20),
    Spec("h264_4k_g250_b2", "h264", 3840, 2160, 30, 1, 250, 2, 8, 20),
    Spec("h264_1080_open", "h264", 1920, 1080, 30, 1, 30, 2, 8, 20, open_gop=True),
    Spec("h264_1080_intra", "h264", 1920, 1080, 30, 1, 1, 0, 8, 10),
    Spec("h264_1080_gop2", "h264", 1920, 1080, 30, 1, 2, 0, 8, 10),
    Spec("hevc_4k_g120_b2", "hevc", 3840, 2160, 30, 1, 120, 2, 8, 20),
    Spec("hevc_1080_main10", "hevc", 1920, 1080, 30, 1, 60, 2, 10, 10),
    Spec("h264_1080_2997", "h264", 1920, 1080, 30000, 1001, 30, 2, 8, 10),
    Spec("h264_1080_aac_beep", "h264", 1920, 1080, 30, 1, 30, 2, 8, 10, aac_beep=True),
]


def _overlay_frame_index(img: np.ndarray, frame_idx: int) -> None:
    """Cyan frame number, upper-right (display index matches encode loop)."""
    pil = Image.fromarray(img)
    draw = ImageDraw.Draw(pil)
    text = str(frame_idx)
    size = max(28, img.shape[0] // 22)
    try:
        font = ImageFont.truetype(str(FRAME_LABEL_FONT), size)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    margin = max(12, img.shape[1] // 160)
    x = img.shape[1] - tw - margin
    y = margin
    draw.text((x, y), text, fill=(0, 255, 255), font=font)
    img[:] = np.asarray(pil)


def render_frame(w: int, h: int, frame_idx: int) -> np.ndarray:
    img = np.full((h, w, 3), 128, np.uint8)
    block_w = w // 64
    block_h = h // 16
    for i in range(32):
        bit = (frame_idx >> (31 - i)) & 1
        x0 = i * block_w
        img[0:block_h, x0 : x0 + block_w] = 255 if bit else 0
    patch_w = w // 16
    for i, (r, g, b, _) in enumerate(PATCH_RGBA):
        x0 = i * patch_w
        img[block_h : 2 * block_h, x0 : x0 + patch_w] = (r, g, b)
    mx = (frame_idx * 7) % max(1, w - 64)
    my = 2 * block_h + (frame_idx * 5) % max(1, h - 2 * block_h - 32)
    img[my : my + 32, mx : mx + 32] = (64, 192, 64)
    _overlay_frame_index(img, frame_idx)
    return img


def encode(spec: Spec) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mp4 = OUT / f"{spec.name}.mp4"
    meta = OUT / f"{spec.name}.expected.json"
    nframes = spec.seconds * spec.fps_num // spec.fps_den
    w, h = spec.width, spec.height

    meta_obj: dict = {
        "name": spec.name,
        "width": w,
        "height": h,
        "fps_num": spec.fps_num,
        "fps_den": spec.fps_den,
        "frames": nframes,
        "patch_rgba_full_range": PATCH_RGBA,
        "block_w": w // 64,
        "block_h": h // 16,
    }
    if spec.aac_beep:
        meta_obj["audio_beep_hz"] = 1000
        meta_obj["audio_beep_duration_s"] = 0.1
        meta_obj["audio_beep_at_integer_seconds"] = list(range(spec.seconds))
    meta.write_text(json.dumps(meta_obj, indent=2) + "\n")

    fps = f"{spec.fps_num}/{spec.fps_den}" if spec.fps_den != 1 else str(spec.fps_num)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{w}x{h}",
        "-r",
        fps,
        "-i",
        "pipe:0",
    ]
    if spec.aac_beep:
        cmd += [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=1000:sample_rate=48000:duration={spec.seconds}",
            "-af",
            "volume=enable='lt(mod(t,1),0.1)'",
        ]
    if spec.codec == "h264":
        cmd += [
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-g",
            str(spec.gop),
            "-bf",
            str(spec.bframes),
        ]
        if spec.open_gop:
            cmd += ["-x264-params", f"keyint={spec.gop}:open-gop=1"]
        else:
            cmd += ["-x264-params", f"keyint={spec.gop}:open-gop=0"]
    else:
        pix = "yuv420p10le" if spec.depth == 10 else "yuv420p"
        cmd += [
            "-c:v",
            "libx265",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            pix,
            "-x265-params",
            f"keyint={spec.gop}:min-keyint={spec.gop}:bframes={spec.bframes}:open-gop=0",
        ]
    if spec.aac_beep:
        cmd += ["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += [
        "-colorspace",
        "bt709",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-movflags",
        "+faststart",
        str(mp4),
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for fi in range(nframes):
        proc.stdin.write(render_frame(w, h, fi).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit(f"ffmpeg failed for {spec.name}")
    print(f"wrote {mp4} ({nframes} frames)")


def main() -> int:
    names = sys.argv[1:]
    specs = SPECS if not names else [s for s in SPECS if s.name in names]
    if not specs:
        print("no matching specs", file=sys.stderr)
        return 1
    for s in specs:
        encode(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
