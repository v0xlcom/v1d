# SPDX-License-Identifier: MIT
"""GPU smoke: NVDEC decodes one presentation frame."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from v1d.ngn import _scrub

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "tests" / "fixtures"
FATBIN = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"


@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestNvdecSmoke(unittest.TestCase):
    def test_decode_frame_zero_1080(self):
        clip = FIXTURES / "h264_1080_g30_b2.mp4"
        self.assertTrue(clip.is_file())
        self.assertTrue(FATBIN.is_file(), f"missing {FATBIN}")
        out = _scrub.nvdec_decode_frame(str(clip), 0, 0, str(FATBIN))
        self.assertEqual(out["presentation_index"], 0)
        self.assertEqual(out["width"], 1920)
        self.assertEqual(out["height"], 1080)
        self.assertGreater(out["pitch"], 0)
        self.assertGreater(out["device_ptr"], 0)
        _scrub.cuda_free(int(out["device_ptr"]))


if __name__ == "__main__":
    unittest.main()
