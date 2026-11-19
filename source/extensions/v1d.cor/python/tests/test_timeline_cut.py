# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest

from test_timeline_sequence import _load_sequence


class TestTimelineCut(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_sequence()
        Clip = self.mod.Clip
        Track = self.mod.Track
        Sequence = self.mod.Sequence
        self.Clip = Clip
        self.Sequence = Sequence
        clip = Clip("a", "/tmp/a.mp4", 0, 0, 99, speed=1.0)
        self.seq = Sequence(
            playhead=50,
            media_frame_count=100,
            timeline_frame_count=200,
            selected_track=0,
            tracks=[Track("t", 0, [clip])],
        )
        self.clip = clip

    def test_cut_middle(self) -> None:
        reason, new_id = self.seq.cut_at(0, 50)
        self.assertEqual(reason, "ok")
        self.assertIsNotNone(new_id)
        self.assertNotEqual(new_id, "a")
        clips = self.seq.tracks[0].clips
        self.assertEqual(len(clips), 2)
        left = next(c for c in clips if c.id == "a")
        right = next(c for c in clips if c.id == new_id)
        self.assertEqual(left.out_frame, 49)
        self.assertEqual(right.in_frame, 50)
        self.assertEqual(right.start_frame, 50)
        self.assertEqual(left.speed, 1.0)
        self.assertEqual(right.speed, 1.0)
        self.assertEqual(left.end_frame + 1, right.start_frame)
        self.assertEqual(right.out_frame, 99)

    def test_cut_double_speed_source_frame(self) -> None:
        self.clip.speed = 2.0
        self.clip.start_frame = 0
        self.clip.in_frame = 0
        self.clip.out_frame = 99
        reason, new_id = self.seq.cut_at(0, 25)
        self.assertEqual(reason, "ok")
        self.assertIsNotNone(new_id)
        left = self.seq.tracks[0].clip_by_id("a")
        right = self.seq.tracks[0].clip_by_id(new_id)
        assert left is not None and right is not None
        self.assertEqual(left.out_frame, 48)
        self.assertEqual(right.in_frame, 50)
        self.assertEqual(left.speed, 2.0)
        self.assertEqual(right.speed, 2.0)

    def test_cut_at_start_unchanged(self) -> None:
        before = [c.id for c in self.seq.tracks[0].clips]
        reason, _ = self.seq.cut_at(0, 0)
        self.assertEqual(reason, "at_start")
        after = [c.id for c in self.seq.tracks[0].clips]
        self.assertEqual(before, after)

    def test_cut_no_clip(self) -> None:
        before = len(self.seq.tracks[0].clips)
        reason, _ = self.seq.cut_at(0, 500)
        self.assertEqual(reason, "no_clip")
        self.assertEqual(len(self.seq.tracks[0].clips), before)


if __name__ == "__main__":
    unittest.main()