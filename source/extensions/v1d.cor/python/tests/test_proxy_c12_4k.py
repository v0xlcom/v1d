# SPDX-License-Identifier: MIT
"""C12 gate: 4K proxy scrub latency + barcode (run with V1D_C12_4K=1)."""

from __future__ import annotations

import os
import random
import tempfile
import time
import unittest
from pathlib import Path

from v1d.ngn import Engine, _scrub

from test_barcode import barcode_from_rgba_proxy, fixture_meta

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "tests" / "fixtures"
FATBIN = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"
CLIP = FIXTURES / "h264_4k_g250_b2.mp4"


def _p95_ms(samples: list[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = int(0.95 * (len(ordered) - 1))
    return ordered[idx]


@unittest.skipUnless(os.environ.get("V1D_C12_4K") == "1", "set V1D_C12_4K=1 for 4K C12 gate")
@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestProxyC124K(unittest.TestCase):
    def test_4k_proxy_scrub_latency_and_barcode(self):
        self.assertTrue(CLIP.is_file())
        self.assertTrue(FATBIN.is_file())
        meta = fixture_meta(FIXTURES, "h264_4k_g250_b2")
        info = _scrub.probe_clip(str(CLIP))
        n = int(info["frames"])
        src_w, src_h = int(info["width"]), int(info["height"])
        out_w, out_h = 960, 540

        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CACHE_HOME"] = td
            _scrub.proxy_build_cache(str(CLIP), 270, 0, str(FATBIN))

            engine = Engine(0, 256, str(FATBIN), 270, 256)
            engine.open_clip(str(CLIP))
            engine.set_output_size(out_w, out_h)
            self.assertTrue(engine.stats().get("proxy_ready"))

            engine.set_scrubbing(True)
            rng = random.Random(42)
            targets = [rng.randrange(n) for _ in range(24)]
            latencies: list[float] = []

            for t in targets:
                engine.request_frame(t)
                t0 = time.perf_counter()
                got = None
                while time.perf_counter() - t0 < 1.0:
                    f = engine.poll()
                    if f and f.get("tier") == "proxy" and f.get("frame") == t:
                        got = f
                        break
                    time.sleep(0.001)
                self.assertIsNotNone(got, f"proxy frame {t}")
                latencies.append(float(got["latency_us"]) / 1000.0)

                px = engine.debug_read_rgba(int(got["ptr"]))
                stride = int(got["stride"])
                decoded = barcode_from_rgba_proxy(px, stride, meta, out_w, out_h)
                self.assertEqual(decoded, t, f"barcode mismatch at frame {t}")

            p95 = _p95_ms(latencies)
            print(f"C12 4K proxy scrub: p95_ms={p95:.2f} n={len(latencies)}")
            self.assertLessEqual(p95, 20.0, f"proxy scrub p95 {p95:.2f} ms exceeds 20 ms")

            engine.set_scrubbing(False)
            engine.request_frame(targets[-1])
            t0 = time.perf_counter()
            exact = None
            while time.perf_counter() - t0 < 30.0:
                f = engine.poll()
                if f and f.get("tier") == "exact" and f.get("frame") == targets[-1]:
                    exact = f
                    break
                time.sleep(0.005)
            self.assertIsNotNone(exact, "expected exact after settle")
            engine.shutdown()


if __name__ == "__main__":
    unittest.main()
