# SPDX-License-Identifier: MIT
"""C12 (Phase 2): proxy tier while scrubbing."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from v1d.ngn import Engine, _scrub

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "tests" / "fixtures"
FATBIN = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"
CLIP = FIXTURES / "h264_1080_gop2.mp4"


@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestProxyC12(unittest.TestCase):
    def test_scrub_publishes_proxy_then_exact(self):
        self.assertTrue(CLIP.is_file())
        self.assertTrue(FATBIN.is_file())
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CACHE_HOME"] = td
            _scrub.proxy_build_cache(str(CLIP), 270, 0, str(FATBIN))

            engine = Engine(0, 128, str(FATBIN), 270)
            engine.open_clip(str(CLIP))
            st = engine.stats()
            self.assertTrue(st.get("proxy_ready"))

            engine.set_scrubbing(True)
            engine.request_frame(50)
            proxy_frame = None
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 2.0:
                f = engine.poll()
                if f and f.get("tier") == "proxy" and f.get("frame") == 50:
                    proxy_frame = f
                    break
                time.sleep(0.005)
            self.assertIsNotNone(proxy_frame, "expected proxy tier while scrubbing")

            engine.set_scrubbing(False)
            engine.request_frame(50)
            exact_frame = None
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 8.0:
                f = engine.poll()
                if f and f.get("tier") == "exact" and f.get("frame") == 50:
                    exact_frame = f
                    break
                time.sleep(0.005)
            self.assertIsNotNone(exact_frame, "expected exact tier after settle")
            engine.shutdown()


if __name__ == "__main__":
    unittest.main()
