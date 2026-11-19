# SPDX-License-Identifier: MIT
"""C11 (Phase 2): .v1dproxy on-disk header, cache path, and build."""

from __future__ import annotations

import os
import struct
import tempfile
import time
import unittest
from pathlib import Path

from v1d.ngn import _scrub

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "tests" / "fixtures"
PROXY_MAGIC = 0x31505631
PROXY_VERSION = 1
HEADER_FMT = "<IIIQQqIIIIIQQ"  # packed ProxyHeader (72 bytes)
HEADER_SIZE = 72


class TestProxyC11(unittest.TestCase):
    def test_cache_path_under_xdg(self):
        clip = FIXTURES / "h264_1080_g30_b2.mp4"
        self.assertTrue(clip.is_file())
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CACHE_HOME"] = td
            path = _scrub.proxy_cache_path(str(clip))
            self.assertIn("/v1d/proxy/", path)
            self.assertTrue(path.endswith(".v1dproxy"))
            path2 = _scrub.proxy_cache_path(str(clip))
            self.assertEqual(path, path2)

    def test_file_size_formula(self):
        w, h, n = 960, 540, 100
        fb = _scrub.proxy_nv12_frame_bytes(w, h)
        self.assertEqual(fb, w * h + w * ((h + 1) // 2))
        total = _scrub.proxy_file_size_bytes(n, fb)
        self.assertEqual(struct.calcsize(HEADER_FMT), HEADER_SIZE)
        self.assertEqual(total, HEADER_SIZE + n * fb + n * 8)

    def test_header_roundtrip_via_struct(self):
        """Document binary layout until ProxyBuilder writes real files."""
        clip = FIXTURES / "h264_1080_g30_b2.mp4"
        st = clip.stat()
        path_hash = 0xDEADBEEF  # placeholder; binding uses fnv internally
        hdr = struct.pack(
            HEADER_FMT,
            PROXY_MAGIC,
            PROXY_VERSION,
            0,
            path_hash,
            st.st_size,
            int(st.st_mtime_ns) if hasattr(st, "st_mtime_ns") else int(st.st_mtime * 1e9),
            1920,
            1080,
            960,
            540,
            30,
            _scrub.proxy_nv12_frame_bytes(960, 540),
            HEADER_SIZE + 30 * _scrub.proxy_nv12_frame_bytes(960, 540),
        )
        self.assertEqual(len(hdr), HEADER_SIZE)
        magic, version, codec, *_rest = struct.unpack(HEADER_FMT, hdr)
        self.assertEqual(magic, PROXY_MAGIC)
        self.assertEqual(version, PROXY_VERSION)
        self.assertEqual(codec, 0)


@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestProxyC11Build(unittest.TestCase):
    def test_build_gop2_cache_size_and_skip_rebuild(self):
        fatbin = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"
        clip = FIXTURES / "h264_1080_gop2.mp4"
        self.assertTrue(clip.is_file())
        self.assertTrue(fatbin.is_file())
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CACHE_HOME"] = td
            t0 = time.perf_counter()
            r1 = _scrub.proxy_build_cache(str(clip), 270, 0, str(fatbin))
            t_build = time.perf_counter() - t0
            self.assertTrue(r1["rebuilt"])
            path = Path(r1["cache_path"])
            self.assertTrue(path.is_file())
            self.assertFalse(path.name.endswith(".building"))
            info = _scrub.probe_clip(str(clip))
            pw = int(round(info["width"] * 270 / info["height"])) & ~1
            fb = _scrub.proxy_nv12_frame_bytes(pw, 270)
            expected = _scrub.proxy_file_size_bytes(int(info["frames"]), fb)
            self.assertEqual(path.stat().st_size, expected)
            self.assertEqual(r1["bytes_written"], expected)
            fps = int(info["frames"]) / max(t_build, 1e-6)
            print(f"C11 build h264_1080_gop2: build_fps={fps:.2f} bytes={expected}")
            r2 = _scrub.proxy_build_cache(str(clip), 270, 0, str(fatbin))
            self.assertFalse(r2["rebuilt"])


if __name__ == "__main__":
    unittest.main()
