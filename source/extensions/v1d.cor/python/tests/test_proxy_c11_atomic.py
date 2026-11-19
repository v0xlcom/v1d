# SPDX-License-Identifier: MIT
"""C11: atomic proxy path — no final file named until rename completes."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from v1d.ngn import _scrub

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "tests" / "fixtures"
FATBIN = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"
CLIP = FIXTURES / "h264_1080_g30_b2.mp4"


@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestProxyC11Atomic(unittest.TestCase):
    def test_no_building_suffix_after_success(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CACHE_HOME"] = td
            r = _scrub.proxy_build_cache(str(CLIP), 270, 0, str(FATBIN))
            final = Path(r["cache_path"])
            self.assertTrue(final.is_file())
            building = Path(str(final) + ".building")
            self.assertFalse(building.exists())

    def test_incomplete_building_not_used_as_cache(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CACHE_HOME"] = td
            cache = Path(_scrub.proxy_cache_path(str(CLIP)))
            cache.parent.mkdir(parents=True, exist_ok=True)
            building = Path(str(cache) + ".building")
            building.write_bytes(b"partial")
            self.assertFalse(cache.exists())
            r = _scrub.proxy_build_cache(str(CLIP), 270, 0, str(FATBIN))
            self.assertTrue(r["rebuilt"])
            self.assertTrue(cache.is_file())
            self.assertGreater(cache.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
