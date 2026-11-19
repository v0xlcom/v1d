# SPDX-License-Identifier: MIT
"""C3: MP4 demuxer matches ffprobe-derived metadata."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from v1d.ngn import _scrub

FIXTURES = Path(__file__).resolve().parents[5] / "tests" / "fixtures"


def _ffprobe(path: Path) -> dict:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,nb_frames",
            "-show_entries",
            "stream_tags=encoder",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    data = json.loads(out)
    st = data["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    sync_out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_packets",
            "-show_entries",
            "packet=flags",
            "-of",
            "csv=p=0",
            str(path),
        ],
        text=True,
    )
    sync_count = sum(1 for line in sync_out.strip().splitlines() if "K" in line)
    return {
        "frames": int(st["nb_frames"]),
        "fps_num": int(num),
        "fps_den": int(den),
        "width": int(st["width"]),
        "height": int(st["height"]),
        "codec": st["codec_name"],
        "sync_count": sync_count,
    }


class TestDemuxC3(unittest.TestCase):
    def test_all_fixtures(self):
        for mp4 in sorted(FIXTURES.glob("*.mp4")):
            ref = _ffprobe(mp4)
            got = _scrub.probe_clip(str(mp4))
            self.assertEqual(got["frames"], ref["frames"], mp4.name)
            self.assertEqual(got["fps_num"], ref["fps_num"], mp4.name)
            self.assertEqual(got["fps_den"], ref["fps_den"], mp4.name)
            self.assertEqual(got["width"], ref["width"], mp4.name)
            self.assertEqual(got["height"], ref["height"], mp4.name)
            self.assertEqual(got["codec"], ref["codec"], mp4.name)
            self.assertEqual(got["sync_count"], ref["sync_count"], mp4.name)
            if ref["codec"] == "hevc" and "main10" in mp4.name:
                self.assertEqual(got["bit_depth"], 10, mp4.name)
            else:
                self.assertEqual(got["bit_depth"], 8, mp4.name)


if __name__ == "__main__":
    unittest.main()
