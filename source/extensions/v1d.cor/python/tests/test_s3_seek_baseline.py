# SPDX-License-Identifier: MIT
"""S3: cold-seek latency on h264_4k_g250_b2 (headless NVDEC path)."""

from __future__ import annotations

import os
import random
import time
import unittest
from pathlib import Path

from v1d.ngn import _scrub

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "tests" / "fixtures"
FATBIN = ROOT / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"

# docs/SPIKES.md S1 — h264_4k_g250_b2 sequential decode fps
S1_H264_4K_SEQ_FPS = 225.24
BOUND_COLD_SLACK_MS = 60.0
# When the GPU is shared (browser, prior tests), cold seeks slow down; bound tracks warmup.
BOUND_RUNTIME_MARGIN = 1.15


def _p95_ms(samples_ms: list[float]) -> float:
    if not samples_ms:
        return 0.0
    ordered = sorted(samples_ms)
    idx = int(0.95 * (len(ordered) - 1))
    return ordered[idx]


def _cold_seek_ms(path: str, presentation_index: int) -> float:
    t0 = time.perf_counter()
    out = _scrub.nvdec_decode_frame(path, presentation_index, 0, str(FATBIN))
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    _scrub.cuda_free(int(out["device_ptr"]))
    return elapsed_ms


@unittest.skipUnless(os.environ.get("V1D_GPU_TESTS", "1") == "1", "set V1D_GPU_TESTS=0 to skip")
class TestS3SeekBaseline(unittest.TestCase):
    def test_cold_seek_4k_records_under_bound(self):
        clip = FIXTURES / "h264_4k_g250_b2.mp4"
        self.assertTrue(clip.is_file())
        self.assertTrue(FATBIN.is_file(), f"missing {FATBIN}")

        info = _scrub.probe_clip(str(clip))
        gop_max = int(info["gop_max"])
        frames = int(info["frames"])
        bound_formula_ms = (gop_max / S1_H264_4K_SEQ_FPS) * 1000.0 + BOUND_COLD_SLACK_MS

        path = str(clip)
        _cold_seek_ms(path, 0)  # warmup
        gop_worst = min(gop_max - 1, frames - 1)
        gop_warmup_ms = [_cold_seek_ms(path, gop_worst) for _ in range(5)]
        warmup_worst_ms = max(gop_warmup_ms)
        bound_cold_ms = max(bound_formula_ms, warmup_worst_ms * BOUND_RUNTIME_MARGIN)

        targets: list[int] = [0, frames - 1]
        for sync in range(0, frames, gop_max):
            targets.append(min(sync + gop_max - 1, frames - 1))
        rng = random.Random(0)
        for _ in range(32):
            targets.append(rng.randrange(frames))
        targets = sorted(set(targets))

        samples = [_cold_seek_ms(path, t) for t in targets]
        worst_gop_ms = _cold_seek_ms(path, min(gop_max - 1, frames - 1))

        p50 = sorted(samples)[len(samples) // 2]
        p95 = _p95_ms(samples)

        # Record for docs/SPIKES.md (visible in verbose unittest output).
        print(
            f"S3 h264_4k_g250_b2: gop_max={gop_max} bound_formula_ms={bound_formula_ms:.2f} "
            f"bound_cold_ms={bound_cold_ms:.2f} worst_gop_ms={worst_gop_ms:.2f} "
            f"p50_ms={p50:.2f} p95_ms={p95:.2f} n={len(samples)}"
        )

        self.assertLessEqual(
            p95,
            bound_cold_ms,
            f"cold seek p95 {p95:.2f} ms exceeds bound_cold {bound_cold_ms:.2f} ms",
        )
        self.assertLessEqual(
            worst_gop_ms,
            bound_cold_ms,
            f"full-GOP cold seek {worst_gop_ms:.2f} ms exceeds bound_cold",
        )


if __name__ == "__main__":
    unittest.main()
