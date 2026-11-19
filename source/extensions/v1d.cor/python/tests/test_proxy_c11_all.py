# SPDX-License-Identifier: MIT
"""C11: build .v1dproxy for every fixture (V1D_C11_ALL=1)."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from v1d.ngn import _scrub

from test_exact_c4 import FIXTURE_NAMES

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "tests" / "fixtures"
FATBIN = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"


@unittest.skipUnless(os.environ.get("V1D_C11_ALL") == "1", "set V1D_C11_ALL=1 for all-fixture C11")
@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestProxyC11AllFixtures(unittest.TestCase):
    def test_build_every_fixture(self):
        self.assertTrue(FATBIN.is_file())
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CACHE_HOME"] = td
            for name in FIXTURE_NAMES:
                mp4 = FIXTURES / f"{name}.mp4"
                if not mp4.is_file():
                    self.skipTest(f"missing {mp4}")
                info = _scrub.probe_clip(str(mp4))
                pw = int(round(int(info["width"]) * 270 / int(info["height"]))) & ~1
                fb = _scrub.proxy_nv12_frame_bytes(pw, 270)
                expected = _scrub.proxy_file_size_bytes(int(info["frames"]), fb)
                t0 = time.perf_counter()
                r1 = _scrub.proxy_build_cache(str(mp4), 270, 0, str(FATBIN))
                elapsed = time.perf_counter() - t0
                fps = int(info["frames"]) / max(elapsed, 1e-6)
                path = Path(r1["cache_path"])
                self.assertTrue(path.is_file())
                self.assertFalse(path.with_suffix(path.suffix + ".building").exists())
                self.assertEqual(path.stat().st_size, expected)
                r2 = _scrub.proxy_build_cache(str(mp4), 270, 0, str(FATBIN))
                self.assertFalse(r2["rebuilt"])
                print(f"C11 {name}: build_fps={fps:.2f} bytes={expected}")


if __name__ == "__main__":
    unittest.main()
