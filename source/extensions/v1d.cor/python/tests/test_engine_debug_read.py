# SPDX-License-Identifier: MIT
"""Engine debug_read_rgba (dev API; must not segfault)."""

from __future__ import annotations

import os
import time
import unittest
from pathlib import Path

from v1d.ngn import Engine

from test_barcode import barcode_from_rgba, fixture_meta

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "tests" / "fixtures"
FATBIN = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"


@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestEngineDebugRead(unittest.TestCase):
    def test_debug_read_rgba_matches_barcode(self):
        clip = FIXTURES / "h264_1080_g30_b2.mp4"
        self.assertTrue(clip.is_file() and FATBIN.is_file())
        meta = fixture_meta(FIXTURES, "h264_1080_g30_b2")
        engine = Engine(0, 64, str(FATBIN))
        try:
            info = engine.open_clip(str(clip))
            w, h = int(info["width"]), int(info["height"])
            engine.set_output_size(w, h)
            target = 42
            engine.set_scrubbing(False)
            engine.request_frame(target)
            frame = None
            for _ in range(400):
                frame = engine.poll()
                if frame is not None and frame["frame"] == target:
                    break
                time.sleep(0.01)
            self.assertIsNotNone(frame)
            raw = engine.debug_read_rgba(int(frame["ptr"]))
            stride = int(frame["stride"])
            self.assertEqual(len(raw), stride * h)
            got = barcode_from_rgba(raw, stride, meta)
            self.assertEqual(got, target)
        finally:
            engine.shutdown()


if __name__ == "__main__":
    unittest.main()
