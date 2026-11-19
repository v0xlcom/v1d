# SPDX-License-Identifier: MIT
"""Upscale subprocess wrapper (fake engine, no weights)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_UPS_PY = Path(__file__).resolve().parents[3] / "v1d.ups/python/v1d/ups"
sys.path.insert(0, str(_UPS_PY))


def _load_module(name: str, filename: str):
    path = _UPS_PY / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_png_io = _load_module("v1d_ups_png_io", "png_io.py")
_run = _load_module("v1d_ups_run", "run.py")


class TestUpsRun(unittest.TestCase):
    def test_fake_upscale_64(self) -> None:
        w, h = 64, 64
        rgba = bytes([10, 20, 30, 255] * (w * h))
        with tempfile.TemporaryDirectory() as td:
            inp = f"{td}/in.png"
            out = f"{td}/out.png"
            _png_io.write_rgba_png(inp, w, h, rgba)
            res = _run.upscale_png(td, "fake", inp, out, timeout_s=30.0)
            self.assertTrue(res.ok, res.error)
            self.assertEqual(res.out_w, w * 4)
            self.assertEqual(res.out_h, h * 4)
            ow, oh, out_rgba = _png_io.read_rgba_png(out)
            self.assertEqual((ow, oh), (256, 256))
            self.assertEqual(out_rgba[0:4], rgba[0:4])


if __name__ == "__main__":
    unittest.main()
