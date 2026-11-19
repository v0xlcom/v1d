# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import unittest
from pathlib import Path

from v1d.ngn import _scrub

ROOT = Path(__file__).resolve().parents[5]
FATBIN = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"


@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestCudaReadRgba(unittest.TestCase):
    def test_alloc_read_roundtrip(self) -> None:
        self.assertTrue(FATBIN.is_file())
        fatbin = str(FATBIN)
        _scrub.cuda_init(0, fatbin)
        try:
            ptr, stride = _scrub.cuda_alloc_rgba(64, 64)
            _scrub.cuda_fill_rgba_frame(ptr, 64, 64, stride, 7)
            raw = _scrub.cuda_read_rgba(ptr, 64, 64, stride)
            self.assertEqual(len(raw), stride * 64)
            _scrub.cuda_free(ptr)
        finally:
            _scrub.cuda_shutdown()

    def test_write_read_roundtrip(self) -> None:
        self.assertTrue(FATBIN.is_file())
        fatbin = str(FATBIN)
        _scrub.cuda_init(0, fatbin)
        try:
            w, h = 64, 64
            src = bytes([11, 22, 33, 255] * (w * h))
            ptr, stride = _scrub.cuda_alloc_rgba(w, h)
            _scrub.cuda_write_rgba(ptr, w, h, stride, src)
            raw = _scrub.cuda_read_rgba(ptr, w, h, stride)
            self.assertEqual(raw[:4], src[:4])
            _scrub.cuda_free(ptr)
        finally:
            _scrub.cuda_shutdown()


if __name__ == "__main__":
    unittest.main()
