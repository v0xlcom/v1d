# SPDX-License-Identifier: MIT
"""C7: hot-path files must not use mutex/condvar."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
PLUGIN = ROOT / "source/extensions/v1d.cor/plugins/v1d.cor"
HOT = [
    "nvdec_decoder.cpp",
    "converter.cpp",
    "frame_cache.cpp",
    "present_ring.cpp",
]
PATTERN = r"std::mutex|lock_guard|unique_lock|condition_variable"


def _grep_hotpath(paths: list[Path]) -> subprocess.CompletedProcess[str]:
    if subprocess.run(["which", "rg"], capture_output=True).returncode == 0:
        return subprocess.run(
            ["rg", PATTERN, *[str(p) for p in paths]],
            capture_output=True,
            text=True,
        )
    # LMDE / minimal hosts without ripgrep: use grep -E (same C7 contract).
    return subprocess.run(
        ["grep", "-En", PATTERN, *[str(p) for p in paths]],
        capture_output=True,
        text=True,
    )


class TestHotpathC7(unittest.TestCase):
    def test_no_mutex_in_hot_path(self):
        paths = [PLUGIN / name for name in HOT if (PLUGIN / name).is_file()]
        self.assertGreater(len(paths), 0)
        proc = _grep_hotpath(paths)
        self.assertEqual(proc.returncode, 1, msg=proc.stdout or proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
