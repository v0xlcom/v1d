# SPDX-License-Identifier: MIT
"""C6: mailbox coalescing under rapid requests."""

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
class TestCoalesceC6(unittest.TestCase):
    def test_latest_wins_under_spam(self):
        clip = FIXTURES / "h264_1080_g30_b2.mp4"
        self.assertTrue(clip.is_file())
        engine = Engine(0, 64, str(FATBIN))
        try:
            info = engine.open_clip(str(clip))
            n = int(info["frames"])
            engine.set_output_size(640, 360)
            engine.set_scrubbing(False)
            for i in range(2000):
                engine.request_frame(i % n)
            for _ in range(100):
                engine.poll()
                time.sleep(0.002)
            final = n - 1
            t0 = time.perf_counter()
            engine.request_frame(final)
            frame = None
            for _ in range(2400):
                frame = engine.poll()
                if frame is not None and frame["frame"] == final:
                    break
                time.sleep(0.005)
            self.assertIsNotNone(frame, "timed out waiting for final frame after spam")
            self.assertEqual(frame["frame"], final)
            stats = engine.stats()
            self.assertGreaterEqual(stats["requests"], 2001)
            self.assertGreater(stats["published"], 0)
            coalesced = int(stats["coalesced"])
            self.assertGreater(
                coalesced,
                0,
                f"mailbox should coalesce under spam (coalesced={coalesced})",
            )
            elapsed = time.perf_counter() - t0
            self.assertLess(elapsed, 12.0)
        finally:
            engine.shutdown()


if __name__ == "__main__":
    unittest.main()
