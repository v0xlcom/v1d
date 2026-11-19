# SPDX-License-Identifier: MIT
"""M0 gate — measure engine reopen on media switch (until C++ source pool lands)."""

from __future__ import annotations

import os
import time
import unittest

GOP2 = os.environ.get("V1D_FIXTURE_DIR", "./spikes/fixtures") + "/h264_gop2_1080.mp4"
GOP30 = os.environ.get("V1D_FIXTURE_DIR", "./spikes/fixtures") + "/h264_gop30_1080.mp4"


@unittest.skipUnless(os.path.isfile(GOP2) and os.path.isfile(GOP30), "fixtures missing")
class TestMediaSwitchM0(unittest.TestCase):
    def test_reopen_switch_ms(self) -> None:
        from v1d.ngn import Engine
        from v1d.ngn.paths import fatbin_path

        fb = fatbin_path()
        engine = Engine(0, 0, str(fb))
        engine.open_clip(GOP2)
        engine.request_frame(0)
        t0 = time.perf_counter()
        engine.open_clip(GOP30)
        engine.request_frame(0)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        engine.close()
        print(f"M0 reopen switch_ms={dt_ms:.2f}")
        self.assertLess(dt_ms, 500.0, "reopen path should stay sub-second for spike record")


if __name__ == "__main__":
    unittest.main()