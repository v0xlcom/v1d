# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import time
import unittest
from pathlib import Path

from v1d.ngn import Engine

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "tests" / "fixtures"
FATBIN = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"


@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestEngineSmoke(unittest.TestCase):
    def test_open_request_poll(self):
        clip = FIXTURES / "h264_1080_g30_b2.mp4"
        self.assertTrue(clip.is_file() and FATBIN.is_file())
        engine = Engine(0, 64, str(FATBIN))
        try:
            info = engine.open_clip(str(clip))
            self.assertEqual(info["width"], 1920)
            engine.set_output_size(640, 360)
            engine.request_frame(0)
            frame = None
            for _ in range(300):
                frame = engine.poll()
                if frame is not None:
                    break
                time.sleep(0.02)
            self.assertIsNotNone(frame)
            self.assertEqual(frame["frame"], 0)
            self.assertIn(frame["tier"], ("exact", "snap"))
            self.assertGreater(frame["ptr"], 0)
            latest = engine.latest_present()
            self.assertIsNotNone(latest)
            self.assertEqual(int(latest["frame"]), int(frame["frame"]))
            self.assertGreater(int(latest["ptr"]), 0)
        finally:
            engine.shutdown()


if __name__ == "__main__":
    unittest.main()
