# SPDX-License-Identifier: MIT

from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest


def _load_project():
    root = pathlib.Path(__file__).resolve().parents[5]
    path = root / "source/extensions/v1d.tl/python/v1d/tl/project.py"
    spec = importlib.util.spec_from_file_location("v1d_tl_project_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestProjectIO(unittest.TestCase):
    def test_round_trip(self) -> None:
        from test_timeline_sequence import _load_sequence

        seq_mod = _load_sequence()
        proj = _load_project()
        seq = seq_mod.Sequence.from_opened_media("/tmp/foo.mp4", 10, track_count=2)
        seq.tracks[0].clips[0].speed = 1.5
        state = seq.to_dict()
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "test.v1d"
            proj.save_project(path, state)
            self.assertFalse(path.with_suffix(path.suffix + ".tmp").exists())
            data, base = proj.load_project(path)
            self.assertEqual(base, path.parent)
            loaded = seq_mod.Sequence.from_dict(data, base_dir=base)
            self.assertEqual(loaded.fps_num, seq.fps_num)
            self.assertEqual(loaded.timeline_frame_count, seq.timeline_frame_count)
            self.assertEqual(len(loaded.tracks), len(seq.tracks))
            a = seq.tracks[0].clips[0]
            b = loaded.tracks[0].clips[0]
            self.assertEqual(b.media_path, a.media_path)
            self.assertAlmostEqual(b.speed, a.speed)
            self.assertEqual(b.start_frame, a.start_frame)
            self.assertEqual(b.in_frame, a.in_frame)
            self.assertEqual(b.out_frame, a.out_frame)

    def test_version_refused(self) -> None:
        from test_timeline_sequence import _load_sequence

        seq_mod = _load_sequence()
        with self.assertRaises(ValueError):
            seq_mod.Sequence.from_dict({"format": "v1d", "version": 99, "sequence": {}})

    def test_unknown_keys_ignored(self) -> None:
        from test_timeline_sequence import _load_sequence

        seq_mod = _load_sequence()
        data = seq_mod.Sequence.from_opened_media("/tmp/x.mp4", 5).to_dict()
        data["future_block"] = {"ignored": True}
        loaded = seq_mod.Sequence.from_dict(data)
        self.assertEqual(len(loaded.tracks), 2)

    def test_missing_media_kept(self) -> None:
        from test_timeline_sequence import _load_sequence

        seq_mod = _load_sequence()
        missing = "/no/such/file/deadbeef.mp4"
        data = {
            "format": "v1d",
            "version": 1,
            "sequence": {
                "timeline_frame_count": 100,
                "tracks": [
                    {
                        "clips": [
                            {
                                "id": "c1",
                                "media": missing,
                                "start": 0,
                                "in": 0,
                                "out": 49,
                                "speed": 1.0,
                            }
                        ]
                    }
                ],
            },
        }
        loaded = seq_mod.Sequence.from_dict(data)
        self.assertEqual(loaded.tracks[0].clips[0].media_path, missing)

    def test_relative_fallback(self) -> None:
        from test_timeline_sequence import _load_sequence

        seq_mod = _load_sequence()
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            media = base / "clip.mp4"
            media.write_bytes(b"fake")
            data = {
                "format": "v1d",
                "version": 1,
                "sequence": {
                    "timeline_frame_count": 50,
                    "tracks": [
                        {
                            "clips": [
                                {
                                    "id": "c1",
                                    "media": "/gone/abs/clip.mp4",
                                    "media_rel": "clip.mp4",
                                    "start": 0,
                                    "in": 0,
                                    "out": 9,
                                }
                            ]
                        }
                    ],
                },
            }
            loaded = seq_mod.Sequence.from_dict(data, base_dir=base)
            self.assertEqual(
                pathlib.Path(loaded.tracks[0].clips[0].media_path).resolve(),
                media.resolve(),
            )

    def test_dirty_bumps_on_mutator_not_read(self) -> None:
        from test_timeline_sequence import _load_sequence

        seq_mod = _load_sequence()
        seq = seq_mod.Sequence.from_opened_media("/tmp/foo.mp4", 20)
        gen0 = seq.dirty_generation
        clip = seq.tracks[0].clips[0]
        seq.cut_at(0, 5)
        self.assertGreater(seq.dirty_generation, gen0)
        gen1 = seq.dirty_generation
        _ = seq.to_dict()
        _ = seq.preview_clip(0)
        self.assertEqual(seq.dirty_generation, gen1)
        seq.mark_clean()
        self.assertEqual(seq.dirty_generation, 0)

    def test_atomic_write_no_tmp(self) -> None:
        proj = _load_project()
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "save.v1d"
            proj.save_project(path, {"format": "v1d", "version": 1, "sequence": {}})
            self.assertTrue(path.is_file())
            leftovers = list(path.parent.glob("*.tmp")) + list(path.parent.glob(".v1d-*.tmp"))
            self.assertEqual(leftovers, [])

    def test_add_clip_lands_free(self) -> None:
        from test_timeline_sequence import _load_sequence

        seq_mod = _load_sequence()
        seq = seq_mod.Sequence.empty(track_count=1, timeline_frame_count=200)
        reason, clip = seq.add_clip(0, "/tmp/a.mp4", 50, want_start=10)
        self.assertEqual(reason, "ok")
        assert clip is not None
        self.assertEqual(clip.start_frame, 10)

    def test_add_clip_nudged_gap(self) -> None:
        from test_timeline_sequence import _load_sequence

        seq_mod = _load_sequence()
        Clip = seq_mod.Clip
        Track = seq_mod.Track
        Sequence = seq_mod.Sequence
        existing = Clip("x", "/tmp/x.mp4", 0, 0, 39)
        seq = Sequence(
            timeline_frame_count=200,
            tracks=[Track("t", 0, [existing])],
        )
        reason, clip = seq.add_clip(0, "/tmp/b.mp4", 30, want_start=20)
        self.assertEqual(reason, "ok")
        assert clip is not None
        self.assertEqual(clip.start_frame, 40)

    def test_add_clip_no_room(self) -> None:
        from test_timeline_sequence import _load_sequence

        seq_mod = _load_sequence()
        Clip = seq_mod.Clip
        Track = seq_mod.Track
        Sequence = seq_mod.Sequence
        full = Clip("x", "/tmp/x.mp4", 0, 0, 99)
        seq = Sequence(
            timeline_frame_count=100,
            tracks=[Track("t", 0, [full])],
        )
        reason, clip = seq.add_clip(0, "/tmp/b.mp4", 50, want_start=0)
        self.assertEqual(reason, "no_room")
        self.assertIsNone(clip)

    def test_add_clip_grows_ruler(self) -> None:
        from test_timeline_sequence import _load_sequence

        seq_mod = _load_sequence()
        seq = seq_mod.Sequence.empty(track_count=1, timeline_frame_count=40)
        before = seq.timeline_frame_count
        reason, clip = seq.add_clip(0, "/tmp/long.mp4", 80, want_start=0)
        self.assertEqual(reason, "ok")
        assert clip is not None
        self.assertGreater(seq.timeline_frame_count, before)
        self.assertGreaterEqual(seq.timeline_frame_count, (clip.end_frame + 1) * seq_mod.TIMELINE_DURATION_SCALE)


if __name__ == "__main__":
    unittest.main()