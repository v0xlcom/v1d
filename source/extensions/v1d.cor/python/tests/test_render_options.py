# SPDX-License-Identifier: MIT
"""Render option validation and size estimate (no Kit)."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest


def _load_options():
    root = pathlib.Path(__file__).resolve().parents[5]
    path = root / "source/extensions/v1d.rnd/python/v1d/rnd/options.py"
    spec = importlib.util.spec_from_file_location("v1d_rnd_options_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_options = _load_options()
RenderOptions = _options.RenderOptions


class TestRenderOptions(unittest.TestCase):
    def test_odd_size_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            odd_width = RenderOptions(
                folder=tmp, filename="a.mp4", width=1919, height=1080
            )
            width_err = odd_width.validate()
            self.assertIsNotNone(width_err)
            assert width_err is not None
            self.assertIn("even", width_err)

            odd_height = RenderOptions(
                folder=tmp, filename="a.mp4", width=1920, height=1081
            )
            height_err = odd_height.validate()
            self.assertIsNotNone(height_err)
            assert height_err is not None
            self.assertIn("even", height_err)

            both = RenderOptions(folder=tmp, filename="a.mp4", width=1279, height=719)
            self.assertIsNotNone(both.validate())

            even = RenderOptions(folder=tmp, filename="a.mp4", width=1920, height=1080)
            self.assertIsNone(even.validate())

    def test_empty_folder_rejected(self) -> None:
        self.assertIsNotNone(RenderOptions(folder="", filename="a.mp4").validate())
        blank = RenderOptions(folder="   ", filename="a.mp4", width=1280, height=720)
        err = blank.validate()
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("folder", err.lower())

    def test_existing_file_requires_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "out.mp4"
            path.write_bytes(b"")
            blocked = RenderOptions(
                folder=tmp,
                filename="out.mp4",
                width=1280,
                height=720,
                overwrite=False,
            )
            err = blocked.validate()
            self.assertIsNotNone(err)
            assert err is not None
            self.assertIn("exists", err)
            allowed = RenderOptions(
                folder=tmp,
                filename="out.mp4",
                width=1280,
                height=720,
                overwrite=True,
            )
            self.assertIsNone(allowed.validate())

    def test_estimate_monotonic_in_bitrate(self) -> None:
        common = dict(
            folder="/tmp",
            filename="v.mp4",
            codec="h264",
            width=1920,
            height=1080,
            fps=30.0,
            overwrite=True,
        )
        samples = []
        for cq in range(15, 36):
            opt = RenderOptions(cq=cq, **common)
            samples.append((opt.bitrate_bps(), opt.estimate_bytes(8.0)))
        for codec in ("h264", "hevc"):
            for width, height in ((1280, 720), (1920, 1080), (3840, 2160)):
                opt = RenderOptions(
                    cq=23,
                    codec=codec,
                    width=width,
                    height=height,
                    folder="/tmp",
                    filename="v.mp4",
                    fps=30.0,
                )
                samples.append((opt.bitrate_bps(), opt.estimate_bytes(8.0)))
        ordered = sorted(samples, key=lambda pair: pair[0])
        estimates = [est for _, est in ordered]
        self.assertEqual(estimates, sorted(estimates))
        for (rate, est), (next_rate, next_est) in zip(ordered, ordered[1:]):
            if next_rate > rate:
                self.assertGreaterEqual(next_est, est)

        low = RenderOptions(cq=35, **common)
        high = RenderOptions(cq=15, **common)
        self.assertLess(low.bitrate_bps(), high.bitrate_bps())
        self.assertLess(low.estimate_bytes(10), high.estimate_bytes(10))

        spans = [high.estimate_bytes(s) for s in (0.0, 0.5, 1.0, 2.0, 10.0)]
        self.assertEqual(spans, sorted(spans))
        self.assertLess(spans[0], spans[-1])


if __name__ == "__main__":
    unittest.main()
