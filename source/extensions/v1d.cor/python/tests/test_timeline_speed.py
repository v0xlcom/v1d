# SPDX-License-Identifier: MIT

from __future__ import annotations

import unittest

from test_timeline_sequence import _load_sequence


class TestTimelineSpeed(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_sequence()
        Clip = self.mod.Clip
        Track = self.mod.Track
        Sequence = self.mod.Sequence
        self.Clip = Clip
        self.SPEED_MIN = self.mod.SPEED_MIN
        self.SPEED_MAX = self.mod.SPEED_MAX
        self.base = Clip("a", "/tmp/a.mp4", 10, 0, 99)
        self.seq = Sequence(
            media_frame_count=100,
            timeline_frame_count=300,
            tracks=[Track("t", 0, [self.base])],
        )

    def _snap(self):
        return self.Clip(
            self.base.id,
            self.base.media_path,
            self.base.start_frame,
            self.base.in_frame,
            self.base.out_frame,
            self.base.speed,
        )

    def test_source_at_double_speed(self) -> None:
        self.base.speed = 2.0
        self.assertEqual(self.base.source_at(10), 0)
        self.assertEqual(self.base.source_at(11), 2)
        self.assertEqual(self.base.source_at(12), 4)

    def test_source_at_half_speed_repeats(self) -> None:
        self.base.speed = 0.5
        self.assertEqual(self.base.source_at(10), 0)
        self.assertEqual(self.base.source_at(11), 0)
        self.assertEqual(self.base.source_at(12), 1)
        self.assertEqual(self.base.source_at(13), 1)

    def test_speed_edge_right_slower(self) -> None:
        ok = self.seq.set_clip_speed_edge(0, "a", self._snap(), "right", 150)
        self.assertTrue(ok)
        self.assertLess(self.base.speed, 1.0)
        self.assertEqual(self.base.in_frame, 0)
        self.assertEqual(self.base.out_frame, 99)

    def test_speed_edge_right_faster(self) -> None:
        ok = self.seq.set_clip_speed_edge(0, "a", self._snap(), "right", 60)
        self.assertTrue(ok)
        self.assertGreater(self.base.speed, 1.0)
        self.assertEqual(self.base.in_frame, 0)
        self.assertEqual(self.base.out_frame, 99)

    def test_speed_clamp_min(self) -> None:
        self.base.start_frame = 0
        self.seq.timeline_frame_count = 500
        ok = self.seq.set_clip_speed_edge(0, "a", self._snap(), "right", 500)
        self.assertTrue(ok)
        self.assertAlmostEqual(self.base.speed, self.SPEED_MIN)
        self.assertEqual(self.base.in_frame, 0)
        self.assertEqual(self.base.out_frame, 99)

    def test_speed_clamp_max(self) -> None:
        ok = self.seq.set_clip_speed_edge(0, "a", self._snap(), "right", 11)
        self.assertTrue(ok)
        self.assertAlmostEqual(self.base.speed, self.SPEED_MAX)
        self.assertEqual(self.base.in_frame, 0)
        self.assertEqual(self.base.out_frame, 99)

    def test_speed_neighbour_stops_right(self) -> None:
        blocker = self.Clip("b", "/tmp/b.mp4", 120, 0, 9)
        self.seq.tracks[0].clips.append(blocker)
        snap = self._snap()
        ok = self.seq.set_clip_speed_edge(0, "a", snap, "right", 200)
        self.assertTrue(ok)
        self.assertLessEqual(self.base.end_frame, blocker.start_frame - 1)

    def test_speed_repeated_from_base_no_stack(self) -> None:
        snap = self._snap()
        self.assertTrue(self.seq.set_clip_speed_edge(0, "a", snap, "right", 80))
        speed_after_one = self.base.speed
        self.assertTrue(self.seq.set_clip_speed_edge(0, "a", snap, "right", 80))
        self.assertAlmostEqual(self.base.speed, speed_after_one)


if __name__ == "__main__":
    unittest.main()