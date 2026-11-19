# SPDX-License-Identifier: MIT
"""C9: lifecycle, clamping, and demux/CUDA error paths."""

from __future__ import annotations

import os
import subprocess
import time
import unittest
from pathlib import Path

from v1d.ngn import Engine, _scrub

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "tests" / "fixtures"
BAD = FIXTURES / "bad"
FATBIN = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"
CLIP = FIXTURES / "h264_1080_g30_b2.mp4"
REL = ROOT / "_build/linux-x86_64/release"
PY = REL / "kit/python/bin/python3"


def _probe(path: Path) -> None:
    _scrub.probe_clip(str(path))


@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestLifecycleC9(unittest.TestCase):
    def setUp(self):
        self._saved_cuda_lib = os.environ.pop("V1D_CUDA_LIB", None)

    def tearDown(self):
        if self._saved_cuda_lib is not None:
            os.environ["V1D_CUDA_LIB"] = self._saved_cuda_lib

    @classmethod
    def setUpClass(cls):
        for name in ("truncated.mp4", "fragmented.mp4", "vp9.mp4", "h264_444.mp4"):
            p = BAD / name
            if not p.is_file():
                raise unittest.SkipTest(f"missing {p}; run tools/gen_bad_fixtures.sh")

    def test_open_close_vram_stable(self):
        self.assertTrue(CLIP.is_file() and FATBIN.is_file())
        engine = Engine(0, 64, str(FATBIN))
        try:
            baseline = None
            for _ in range(50):
                engine.open_clip(str(CLIP))
                stats = engine.stats()
                free = int(stats["vram_free_bytes"])
                if baseline is None:
                    baseline = free
                else:
                    self.assertLessEqual(abs(free - baseline), 16 * 1024 * 1024)
                engine.close()
        finally:
            engine.shutdown()

    def test_shutdown_idempotent_and_fast(self):
        engine = Engine(0, 64, str(FATBIN))
        engine.open_clip(str(CLIP))
        engine.close()
        t0 = time.perf_counter()
        engine.shutdown()
        engine.shutdown()
        self.assertLess(time.perf_counter() - t0, 2.0)

    def test_request_past_end_clamps(self):
        engine = Engine(0, 64, str(FATBIN))
        try:
            info = engine.open_clip(str(CLIP))
            n = int(info["frames"])
            last = n - 1
            engine.set_output_size(320, 180)
            engine.request_frame(last + 10_000)
            frame = None
            for _ in range(400):
                frame = engine.poll()
                if frame is not None:
                    break
                time.sleep(0.01)
            self.assertIsNotNone(frame)
            self.assertEqual(frame["frame"], last)
        finally:
            engine.shutdown()

    def test_probe_errors(self):
        with self.assertRaisesRegex(RuntimeError, "truncated MP4"):
            _probe(BAD / "truncated.mp4")
        with self.assertRaisesRegex(RuntimeError, "fragmented MP4"):
            _probe(BAD / "fragmented.mp4")
        with self.assertRaisesRegex(RuntimeError, "VP9"):
            _probe(BAD / "vp9.mp4")
        with self.assertRaisesRegex(RuntimeError, "4:2:0"):
            _probe(BAD / "h264_444.mp4")

    def test_missing_cuda_driver(self):
        self.assertTrue(PY.is_file())
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REL / "exts/v1d.cor")
        env["LD_LIBRARY_PATH"] = str(REL / "kit")
        env["V1D_CUDA_LIB"] = "/nonexistent"
        code = (
            "from v1d.ngn import Engine\n"
            f"e=Engine(0,0,'{FATBIN}')\n"
            f"e.open_clip('{CLIP}')\n"
        )
        proc = subprocess.run([str(PY), "-c", code], env=env, capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        err = proc.stderr + proc.stdout
        self.assertIn("CUDA driver library", err)


if __name__ == "__main__":
    unittest.main()
