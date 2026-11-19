# SPDX-License-Identifier: MIT
"""C8: record perf gates (also updates docs/PERF.md when V1D_WRITE_PERF=1)."""

from __future__ import annotations

import os
import statistics
import time
import unittest
from pathlib import Path

from v1d.ngn import Engine

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "tests" / "fixtures"
FATBIN = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"
CLIP_1080 = FIXTURES / "h264_1080_g30_b2.mp4"
CLIP_4K = FIXTURES / "h264_4k_g250_b2.mp4"
BOUND_COLD_MS = 1165.49
S1_SINGLE_IDR_MS = 26.99
POLL_SAMPLES = 5000


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = int(0.95 * (len(values) - 1))
    return values[idx]


@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestPerfC8(unittest.TestCase):
    def test_c8_gates(self):
        self.assertTrue(CLIP_1080.is_file() and CLIP_4K.is_file() and FATBIN.is_file())
        engine = Engine(0, 256, str(FATBIN))
        try:
            info = engine.open_clip(str(CLIP_1080))
            engine.set_output_size(1920, 1080)
            engine.set_scrubbing(False)

            # Warm cache at frame 0
            engine.request_frame(0)
            for _ in range(400):
                if engine.poll() is not None:
                    break
                time.sleep(0.005)

            hit_lat_ms: list[float] = []
            for _ in range(30):
                engine.request_frame(0)
                t0 = time.perf_counter()
                for _ in range(200):
                    f = engine.poll()
                    if f is not None:
                        hit_lat_ms.append((time.perf_counter() - t0) * 1000.0)
                        break
                    time.sleep(0.0005)
            hit_p95 = p95(hit_lat_ms)
            self.assertLessEqual(hit_p95, 4.0, f"cache-hit publish p95 {hit_p95:.2f} ms")

            # Snap (scrubbing) near non-IDR
            engine.set_scrubbing(True)
            snap_lat_ms: list[float] = []
            for target in (17, 23, 41):
                engine.request_frame(target)
                t0 = time.perf_counter()
                for _ in range(300):
                    f = engine.poll()
                    if f is not None:
                        snap_lat_ms.append((time.perf_counter() - t0) * 1000.0)
                        break
                    time.sleep(0.002)
            snap_p95 = p95(snap_lat_ms)
            self.assertLessEqual(
                snap_p95, S1_SINGLE_IDR_MS + 20.0, f"snap p95 {snap_p95:.2f} ms"
            )

            engine.close()
            info4k = engine.open_clip(str(CLIP_4K))
            engine.set_output_size(1280, 720)
            engine.set_scrubbing(False)
            cold_lat_ms: list[float] = []
            syncs = [0, 250, 500, 750, 1000]
            for target in syncs:
                if target >= int(info4k["frames"]):
                    continue
                engine.request_frame(target)
                t0 = time.perf_counter()
                for _ in range(3000):
                    f = engine.poll()
                    if f is not None and f["frame"] == target:
                        cold_lat_ms.append((time.perf_counter() - t0) * 1000.0)
                        break
                    time.sleep(0.002)
            cold_p95 = p95(cold_lat_ms)
            self.assertLessEqual(cold_p95, BOUND_COLD_MS, f"cold seek p95 {cold_p95:.2f} ms")

            poll_us: list[float] = []
            for _ in range(POLL_SAMPLES):
                t0 = time.perf_counter()
                engine.poll()
                poll_us.append((time.perf_counter() - t0) * 1e6)
            poll_p95 = p95(poll_us)
            self.assertLessEqual(poll_p95, 50.0, f"poll p95 {poll_p95:.1f} µs")

            if os.environ.get("V1D_WRITE_PERF") == "1":
                perf = ROOT / "docs/PERF.md"
                text = perf.read_text()
                repl = {
                    "| C8 | Cache-hit publish p95 @ 1080p output | ≤ 4 ms | TBD |": (
                        f"| C8 | Cache-hit publish p95 @ 1080p output | ≤ 4 ms | {hit_p95:.2f} ms |"
                    ),
                    "| C8 | Cold seek p95 | ≤ `bound_cold` | TBD |": (
                        f"| C8 | Cold seek p95 | ≤ `bound_cold` | {cold_p95:.2f} ms |"
                    ),
                    "| C8 | Snap p95 | ≤ S1 single-IDR + 20 ms | TBD |": (
                        f"| C8 | Snap p95 | ≤ S1 single-IDR + 20 ms | {snap_p95:.2f} ms |"
                    ),
                    "| C8 | `poll()` p95 | ≤ 50 µs | TBD |": (
                        f"| C8 | `poll()` p95 | ≤ 50 µs | {poll_p95:.1f} µs |"
                    ),
                }
                for old, new in repl.items():
                    text = text.replace(old, new)
                perf.write_text(text)
        finally:
            engine.shutdown()


if __name__ == "__main__":
    unittest.main()
