# SPDX-License-Identifier: MIT
"""C4: exact decode barcode matches presentation index."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from v1d.ngn import _scrub

from test_barcode import barcode_from_rgba, c4_target_indices, fixture_meta

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "tests" / "fixtures"
FATBIN = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"

FIXTURE_NAMES = [
    "h264_1080_g30_b2",
    "h264_1080_intra",
    "h264_1080_gop2",
    "h264_1080_open",
    "h264_1080_2997",
    "h264_4k_g250_b2",
    "hevc_4k_g120_b2",
]

# 10-bit HEVC barcode band is lossy at full-res convert; covered by C5 patches.


@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestExactC4(unittest.TestCase):
    def _run_fixture(self, name: str) -> None:
        mp4 = FIXTURES / f"{name}.mp4"
        if not mp4.is_file():
            self.skipTest(f"missing {mp4}")
        if name == "h264_1080_gop2" and not (FIXTURES / "h264_1080_gop2.expected.json").is_file():
            self.skipTest("run: python3 tools/gen_fixtures.py h264_1080_gop2")

        meta = fixture_meta(FIXTURES, name)
        is_4k = meta["width"] >= 3840
        info = _scrub.probe_clip(str(mp4))
        n = int(info["frames"])
        w, h = int(info["width"]), int(info["height"])

        indices = c4_target_indices(n, mp4, is_4k)
        if os.environ.get("V1D_C4_QUICK") == "1":
            indices = indices[: min(40, len(indices))]

        stride = w * 4
        for target in indices:
            raw = _scrub.nvdec_convert_frame_rgba(str(mp4), target, w, h, 0, str(FATBIN))
            got = barcode_from_rgba(raw, stride, meta)
            self.assertEqual(got, target, f"{name} frame {target} barcode {got}")

    def test_all_fixtures(self):
        for name in FIXTURE_NAMES:
            with self.subTest(name=name):
                self._run_fixture(name)


if __name__ == "__main__":
    unittest.main()
