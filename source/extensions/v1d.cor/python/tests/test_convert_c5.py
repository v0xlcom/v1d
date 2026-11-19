# SPDX-License-Identifier: MIT
"""C5: color patches within tolerance after NV12 convert (limited BT.709)."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from v1d.ngn import _scrub

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "tests" / "fixtures"
FATBIN = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"

TOL = 20


def _rgba_at(pixels: bytes, stride: int, x: int, y: int) -> tuple[int, int, int, int]:
    off = y * stride + x * 4
    return pixels[off], pixels[off + 1], pixels[off + 2], pixels[off + 3]


@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestConvertC5(unittest.TestCase):
    def test_h264_1080_patch_colors(self):
        name = "h264_1080_g30_b2"
        mp4 = FIXTURES / f"{name}.mp4"
        meta = FIXTURES / f"{name}.expected.json"
        self.assertTrue(mp4.is_file() and meta.is_file())
        spec = json.loads(meta.read_text())
        w, h = spec["width"], spec["height"]
        patch_w = w // 16
        block_h = spec["block_h"]
        expected = spec["patch_rgba_full_range"]

        raw = _scrub.nvdec_convert_frame_rgba(str(mp4), 0, w, h, 0, str(FATBIN))
        stride = w * 4
        for i, (er, eg, eb, ea) in enumerate(expected):
            cx = i * patch_w + patch_w // 2
            cy = block_h + (block_h // 2)
            r, g, b, a = _rgba_at(raw, stride, cx, cy)
            self.assertEqual(a, 255)
            self.assertLessEqual(abs(r - er), TOL, f"patch {i} R")
            self.assertLessEqual(abs(g - eg), TOL, f"patch {i} G")
            self.assertLessEqual(abs(b - eb), TOL, f"patch {i} B")


if __name__ == "__main__":
    unittest.main()
