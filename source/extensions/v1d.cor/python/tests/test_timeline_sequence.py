# SPDX-License-Identifier: MIT
"""Timeline clip / track model (PLAN_CLIP_N_2_TRACK)."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


def _load_sequence():
    root = pathlib.Path(__file__).resolve().parents[5]
    path = root / "source/extensions/v1d.tl/python/v1d/tl/sequence.py"
    spec = importlib.util.spec_from_file_location("v1d_tl_sequence_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_sequence = _load_sequence()
Clip = _sequence.Clip
Sequence = _sequence.Sequence
MAX_TRACKS = _sequence.MAX_TRACKS


class TestTimelineSequence(unittest.TestCase):
    def _seq(self, frames: int = 100) -> Sequence:
        return Sequence.from_opened_media("/tmp/clip.mp4", frames)

    def test_source_mapping(self) -> None:
        seq = self._seq(60)
        clip = seq.tracks[0].clips[0]
        clip.start_frame = 10
        clip.in_frame = 5
        clip.out_frame = 20
        self.assertEqual(clip.source_at(10), 5)
        self.assertEqual(clip.source_at(15), 10)
        self.assertIsNone(clip.source_at(9))
        self.assertEqual(clip.sequence_at_source(10), 15)

    def test_move_body_leaves_in_out(self) -> None:
        seq = self._seq(100)
        clip = seq.tracks[0].clips[0]
        before_in, before_out = clip.in_frame, clip.out_frame
        self.assertTrue(seq.move_clip_body(0, clip.id, 12))
        self.assertEqual(clip.start_frame, 12)
        self.assertEqual(clip.in_frame, before_in)
        self.assertEqual(clip.out_frame, before_out)

    def test_trim_left_shifts_start_and_in(self) -> None:
        seq = self._seq(100)
        clip = seq.tracks[0].clips[0]
        end_before = clip.end_frame
        self.assertTrue(seq.trim_left(0, clip.id, 8))
        self.assertEqual(clip.start_frame, 8)
        self.assertEqual(clip.in_frame, 8)
        self.assertEqual(clip.out_frame, 99)
        self.assertEqual(clip.end_frame, end_before)

    def test_trim_clamps_to_one_frame(self) -> None:
        seq = self._seq(100)
        clip = seq.tracks[0].clips[0]
        end_before = clip.end_frame
        self.assertTrue(seq.trim_left(0, clip.id, 10000))
        self.assertEqual(clip.duration, 1)
        self.assertEqual(clip.end_frame, end_before)
        self.assertEqual(clip.out_frame, 99)
        self.assertTrue(seq.trim_right(1, seq.tracks[1].clips[0].id, -10000))
        other = seq.tracks[1].clips[0]
        self.assertEqual(other.duration, 1)
        self.assertEqual(other.start_frame, 0)
        self.assertEqual(other.in_frame, 0)

    def test_trim_left_lands_on_ruler_frame(self) -> None:
        seq = self._seq(100)
        clip = seq.tracks[0].clips[0]
        snap = Clip(
            id=clip.id,
            media_path=clip.media_path,
            start_frame=clip.start_frame,
            in_frame=clip.in_frame,
            out_frame=clip.out_frame,
        )
        end_before = clip.end_frame
        frame = 12
        self.assertTrue(seq.restore_and_trim_left(0, clip.id, snap, frame - snap.start_frame))
        self.assertEqual(clip.start_frame, frame)
        self.assertEqual(clip.in_frame, frame)
        self.assertEqual(clip.out_frame, snap.out_frame)
        self.assertEqual(clip.end_frame, end_before)

    def test_trim_right_edge_on_tick(self) -> None:
        seq = self._seq(100)
        clip = seq.tracks[0].clips[0]
        snap = Clip(
            id=clip.id,
            media_path=clip.media_path,
            start_frame=clip.start_frame,
            in_frame=clip.in_frame,
            out_frame=clip.out_frame,
        )
        frame = 80
        delta = (frame - 1) - snap.end_frame
        self.assertTrue(seq.restore_and_trim_right(0, clip.id, snap, delta))
        self.assertEqual(clip.end_frame, frame - 1)
        self.assertEqual(clip.start_frame, snap.start_frame)
        self.assertEqual(clip.in_frame, snap.in_frame)

    def test_trim_extend_restores_media_frames(self) -> None:
        seq = self._seq(100)
        clip = seq.tracks[0].clips[0]
        snap = Clip(
            id=clip.id,
            media_path=clip.media_path,
            start_frame=clip.start_frame,
            in_frame=clip.in_frame,
            out_frame=clip.out_frame,
        )
        self.assertTrue(seq.trim_left(0, clip.id, 15))
        shortened = Clip(
            id=clip.id,
            media_path=clip.media_path,
            start_frame=clip.start_frame,
            in_frame=clip.in_frame,
            out_frame=clip.out_frame,
        )
        self.assertTrue(seq.restore_and_trim_left(0, clip.id, shortened, -10))
        self.assertEqual(clip.start_frame, 5)
        self.assertEqual(clip.in_frame, 5)
        self.assertEqual(clip.out_frame, 99)
        self.assertEqual(clip.end_frame, shortened.end_frame)
        self.assertTrue(seq.restore_and_trim_right(0, clip.id, snap, -15))
        self.assertEqual(clip.out_frame, 84)
        pulled = Clip(
            id=clip.id,
            media_path=clip.media_path,
            start_frame=clip.start_frame,
            in_frame=clip.in_frame,
            out_frame=clip.out_frame,
        )
        self.assertTrue(seq.restore_and_trim_right(0, clip.id, pulled, 10))
        self.assertEqual(clip.out_frame, 94)
        self.assertEqual(clip.start_frame, 0)
        self.assertEqual(clip.in_frame, 0)

    def test_trim_extend_stops_at_neighbor(self) -> None:
        seq = self._seq(200)
        first = seq.tracks[0].clips[0]
        self.assertTrue(seq.trim_right(0, first.id, 40 - first.end_frame))
        self.assertEqual(first.end_frame, 40)
        second = Clip(
            id="b",
            media_path=seq.media_path,
            start_frame=80,
            in_frame=40,
            out_frame=60,
        )
        seq.tracks[0].clips.append(second)
        end_before = second.end_frame
        self.assertTrue(seq.trim_left(0, second.id, -1000))
        self.assertEqual(second.start_frame, first.end_frame + 1)
        self.assertEqual(second.end_frame, end_before)
        self.assertLess(second.in_frame, 40)
        self.assertTrue(seq.trim_right(0, first.id, 1000))
        self.assertEqual(first.end_frame, second.start_frame - 1)
        self.assertEqual(first.start_frame, 0)

    def test_trim_right_stops_at_sequence_end(self) -> None:
        seq = self._seq(50)
        clip = seq.tracks[0].clips[0]
        clip.start_frame = 60
        clip.in_frame = 0
        clip.out_frame = 10
        self.assertTrue(seq.trim_right(0, clip.id, 1000))
        self.assertEqual(clip.end_frame, seq.sequence_frame_max)
        self.assertEqual(clip.start_frame, 60)
        self.assertEqual(clip.in_frame, 0)
        self.assertLessEqual(clip.out_frame, 49)

    def test_trim_right_only_out(self) -> None:
        seq = self._seq(100)
        clip = seq.tracks[0].clips[0]
        start_before = clip.start_frame
        in_before = clip.in_frame
        self.assertTrue(seq.trim_right(0, clip.id, -10))
        self.assertEqual(clip.out_frame, 89)
        self.assertEqual(clip.start_frame, start_before)
        self.assertEqual(clip.in_frame, in_before)

    def test_same_track_overlap_rejected(self) -> None:
        seq = self._seq(200)
        t = seq.tracks[0]
        second = Clip(
            id="b",
            media_path=seq.media_path,
            start_frame=50,
            in_frame=0,
            out_frame=49,
        )
        t.clips.append(second)
        self.assertFalse(seq.move_clip_body(0, second.id, -30))

    def test_duplicate_independent_start(self) -> None:
        seq = self._seq(80)
        self.assertEqual(len(seq.tracks), 2)
        a = seq.tracks[0].clips[0]
        b = seq.tracks[1].clips[0]
        self.assertNotEqual(a.id, b.id)
        self.assertTrue(seq.move_clip_body(1, b.id, 25))
        self.assertEqual(b.start_frame, 25)
        self.assertEqual(a.start_frame, 0)

    def test_selected_source(self) -> None:
        seq = self._seq(100)
        seq.selected_track = 1
        clip = seq.tracks[1].clips[0]
        clip.start_frame = 20
        self.assertEqual(seq.source_for_selected(25), 5)

    def test_timeline_twice_media_length(self) -> None:
        seq = self._seq(50)
        self.assertEqual(seq.media_frame_count, 50)
        self.assertEqual(seq.timeline_frame_count, 100)
        self.assertEqual(seq.sequence_frame_max, 99)
        clip = seq.tracks[0].clips[0]
        self.assertEqual(clip.duration, 50)
        self.assertTrue(seq.move_clip_body(0, clip.id, 40))
        self.assertEqual(clip.start_frame, 40)
        self.assertTrue(seq.move_clip_body(0, clip.id, 11))
        self.assertEqual(clip.start_frame, 50)
        self.assertEqual(clip.end_frame, 99)
        self.assertTrue(seq.move_clip_body(0, clip.id, -1000))
        self.assertEqual(clip.start_frame, 0)

    def test_track_enable_flags_default_true(self) -> None:
        seq = self._seq(60)
        for track in seq.tracks:
            self.assertTrue(track.video_enabled)
            self.assertTrue(track.audio_enabled)

    def test_duplicate_track_resets_enable_flags(self) -> None:
        seq = self._seq(60)
        seq.tracks[0].video_enabled = False
        seq.tracks[0].audio_enabled = False
        dup = seq.duplicate_track()
        self.assertTrue(dup.video_enabled)
        self.assertTrue(dup.audio_enabled)

    def test_preview_source_prefers_selected_track(self) -> None:
        seq = self._seq(100)
        t0 = seq.tracks[0].clips[0]
        t1 = seq.tracks[1].clips[0]
        t0.start_frame = 0
        t1.start_frame = 0
        seq.selected_track = 1
        t0.in_frame = 0
        t0.out_frame = 99
        t1.in_frame = 10
        t1.out_frame = 99
        self.assertEqual(seq.preview_source(5), 15)

    def test_preview_source_skips_selected_when_video_off(self) -> None:
        seq = self._seq(100)
        seq.selected_track = 0
        seq.tracks[0].video_enabled = False
        top = seq.tracks[0].clips[0]
        bottom = seq.tracks[1].clips[0]
        top.in_frame = 50
        top.out_frame = 99
        bottom.in_frame = 0
        bottom.out_frame = 99
        self.assertEqual(seq.preview_source(10), 10)

    def test_preview_source_none_past_the_block(self) -> None:
        seq = self._seq(100)
        for track in seq.tracks:
            clip = track.clips[0]
            self.assertTrue(seq.trim_right(track.index, clip.id, -40))
        self.assertIsNone(seq.preview_source(80))
        self.assertEqual(seq.preview_source(10), 10)

    def test_sequence_playback_span_asymmetric_tracks(self) -> None:
        seq = self._seq(1000)
        t1 = seq.tracks[0].clips[0]
        self.assertTrue(seq.trim_right(0, t1.id, -(t1.out_frame - 226)))
        self.assertEqual(seq.sequence_playback_span(), (0, 999))
        self.assertEqual(seq.preview_source(227), 227)

    def test_sequence_playback_span_video_off_shrinks(self) -> None:
        seq = self._seq(100)
        t0 = seq.tracks[0].clips[0]
        self.assertTrue(seq.trim_right(0, t0.id, -(t0.out_frame - 22)))
        seq.tracks[1].video_enabled = False
        self.assertEqual(seq.sequence_playback_span(), (0, 22))

    def test_preview_source_none_when_all_video_off(self) -> None:
        seq = self._seq(100)
        seq.tracks[0].video_enabled = False
        seq.tracks[1].video_enabled = False
        self.assertIsNone(seq.preview_source(10))

    def test_preview_source_ignores_audio_enabled(self) -> None:
        seq = self._seq(100)
        seq.selected_track = 0
        seq.tracks[0].audio_enabled = False
        clip = seq.tracks[0].clips[0]
        clip.start_frame = 0
        self.assertEqual(seq.preview_source(5), 5)

    def test_move_track_swaps_and_keeps_selection(self) -> None:
        seq = self._seq(80)
        id0 = seq.tracks[0].id
        id1 = seq.tracks[1].id
        seq.tracks[0].video_enabled = False
        seq.tracks[1].audio_enabled = False
        seq.selected_track = 1
        b_start = seq.tracks[1].clips[0].start_frame
        self.assertTrue(seq.move_track(0, 1))
        self.assertEqual(seq.tracks[0].id, id1)
        self.assertEqual(seq.tracks[1].id, id0)
        self.assertEqual(seq.tracks[0].index, 0)
        self.assertEqual(seq.tracks[1].index, 1)
        self.assertTrue(seq.tracks[0].video_enabled)
        self.assertFalse(seq.tracks[0].audio_enabled)
        self.assertFalse(seq.tracks[1].video_enabled)
        self.assertTrue(seq.tracks[1].audio_enabled)
        self.assertEqual(seq.tracks[0].clips[0].start_frame, b_start)
        self.assertEqual(seq.selected_track, 0)
        self.assertEqual(seq.tracks[seq.selected_track].id, id1)

    def test_move_clip_to_track_nudges_when_blocked_at_want(self) -> None:
        seq = self._seq(200)
        moving = seq.tracks[0].clips[0]
        moving.out_frame = 49
        dest = seq.tracks[1]
        dest.clips.clear()
        dest.clips.append(
            Clip(
                id="block",
                media_path=seq.media_path,
                start_frame=0,
                in_frame=0,
                out_frame=49,
            )
        )
        self.assertTrue(seq.move_clip_to_track(moving.id, 1))
        landed = dest.clip_by_id(moving.id)
        self.assertIsNotNone(landed)
        assert landed is not None
        self.assertEqual(landed.start_frame, 50)
        self.assertIsNone(seq.tracks[0].clip_by_id(moving.id))

    def test_free_start_want_unchanged_when_fits(self) -> None:
        seq = self._seq(300)
        clip = seq.tracks[0].clips[0]
        clip.out_frame = 49
        track = seq.tracks[1]
        track.clips.clear()
        self.assertEqual(seq.free_start_on_track(1, clip.duration, 80), 80)

    def test_move_clip_to_free_spot_keeps_in_out(self) -> None:
        seq = self._seq(300)
        moving = seq.tracks[0].clips[0]
        moving.out_frame = 79
        seq.tracks[1].clips.clear()
        before_in, before_out = moving.in_frame, moving.out_frame
        want = 40
        reason, start = seq.move_clip(moving.id, 1, want)
        self.assertEqual(reason, "ok")
        self.assertEqual(start, want)
        landed = seq.tracks[1].clip_by_id(moving.id)
        self.assertIsNotNone(landed)
        assert landed is not None
        self.assertEqual(landed.start_frame, want)
        self.assertEqual(landed.in_frame, before_in)
        self.assertEqual(landed.out_frame, before_out)
        self.assertEqual(seq.selected_track, 1)

    def test_move_clip_nudges_to_nearest_gap(self) -> None:
        seq = self._seq(400)
        moving = seq.tracks[0].clips[0]
        moving.out_frame = 39
        dest = seq.tracks[1]
        dest.clips.clear()
        dest.clips.append(
            Clip(
                id="block",
                media_path=seq.media_path,
                start_frame=50,
                in_frame=0,
                out_frame=29,
            )
        )
        want = 55
        reason, start = seq.move_clip(moving.id, 1, want)
        self.assertEqual(reason, "ok")
        self.assertEqual(start, 80)
        landed = seq.tracks[1].clip_by_id(moving.id)
        self.assertIsNotNone(landed)
        assert landed is not None
        self.assertEqual(landed.start_frame, 80)

    def test_free_start_tie_prefers_earlier_gap(self) -> None:
        seq = self._seq(400)
        track = seq.tracks[0]
        track.clips.clear()
        track.clips.append(
            Clip(id="c", media_path=seq.media_path, start_frame=20, in_frame=0, out_frame=9)
        )
        # Before c at 10 and after c at 30 are both 10 frames from 20.
        self.assertEqual(seq.free_start_on_track(0, 10, 20), 10)

    def test_free_start_flush_before_next_block(self) -> None:
        seq = self._seq(100)
        track = seq.tracks[1]
        track.clips.clear()
        track.clips.append(
            Clip(id="b", media_path=seq.media_path, start_frame=150, in_frame=0, out_frame=49)
        )
        # Block of 40 dropped at 130 overlaps b; no room after b (ends at 199 = max).
        self.assertEqual(seq.free_start_on_track(1, 40, 130), 110)

    def test_move_clip_no_room_unchanged(self) -> None:
        seq = self._seq(60)
        moving = seq.tracks[0].clips[0]
        moving.out_frame = 59
        seq.tracks[1].clips.clear()
        dest = seq.tracks[1]
        for start, cid in ((0, "a"), (60, "b")):
            dest.clips.append(
                Clip(
                    id=cid,
                    media_path=seq.media_path,
                    start_frame=start,
                    in_frame=0,
                    out_frame=59,
                )
            )
        snap_start = moving.start_frame
        reason, _ = seq.move_clip(moving.id, 1, 0)
        self.assertEqual(reason, "no_room")
        self.assertIs(seq.tracks[0].clip_by_id(moving.id), moving)
        self.assertEqual(moving.start_frame, snap_start)

    def test_move_clip_same_track_reason(self) -> None:
        seq = self._seq(200)
        clip = seq.tracks[0].clips[0]
        clip.out_frame = 49
        reason, start = seq.move_clip(clip.id, 0, clip.start_frame)
        self.assertEqual(reason, "same_track")
        self.assertEqual(start, clip.start_frame)

    def test_move_clip_clamps_want_start(self) -> None:
        seq = self._seq(100)
        clip = seq.tracks[0].clips[0]
        clip.out_frame = 49
        seq.tracks[1].clips.clear()
        seq.tracks[0].clips[:] = [clip]
        reason, start = seq.move_clip(clip.id, 1, 10_000)
        self.assertEqual(reason, "ok")
        self.assertEqual(start, 150)

    def test_move_clip_round_trip_id(self) -> None:
        seq = self._seq(300)
        clip = seq.tracks[0].clips[0]
        clip.out_frame = 59
        seq.tracks[1].clips.clear()
        cid = clip.id
        seq.move_clip(cid, 1, 30)
        seq.move_clip(cid, 0, 45)
        self.assertIs(seq.tracks[0].clip_by_id(cid), clip)
        self.assertEqual(clip.start_frame, 45)

    def test_two_clips_preview_and_trim_stops(self) -> None:
        seq = self._seq(400)
        track = seq.tracks[0]
        first = track.clips[0]
        first.out_frame = 49
        second = Clip(
            id="second",
            media_path=seq.media_path,
            start_frame=80,
            in_frame=30,
            out_frame=59,
        )
        track.clips.append(second)
        self.assertIs(track.clip_at_sequence(90), second)
        self.assertEqual(seq.preview_source(90), 40)
        self.assertTrue(seq.trim_left(0, second.id, -50))
        self.assertEqual(second.start_frame, 50)
        self.assertTrue(seq.trim_right(0, first.id, 100))
        self.assertEqual(first.out_frame, 49)

    def test_add_track_below(self) -> None:
        seq = self._seq(100)
        self.assertEqual(len(seq.tracks), 2)
        added = seq.add_track(0, above=False)
        self.assertIsNotNone(added)
        assert added is not None
        self.assertEqual(len(seq.tracks), 3)
        self.assertEqual(added.index, 1)
        self.assertEqual(added.clips, [])
        self.assertEqual(seq.selected_track, 1)
        self.assertEqual(seq.tracks[1].index, 1)
        self.assertEqual(seq.tracks[2].index, 2)

    def test_add_track_above(self) -> None:
        seq = self._seq(100)
        t1_id = seq.tracks[1].id
        added = seq.add_track(1, above=True)
        self.assertIsNotNone(added)
        assert added is not None
        self.assertEqual(added.index, 1)
        self.assertEqual(seq.tracks[2].id, t1_id)
        self.assertEqual(seq.selected_track, 1)

    def test_add_track_above_first_row(self) -> None:
        seq = self._seq(100)
        t1_id = seq.tracks[0].id
        added = seq.add_track(0, above=True)
        self.assertIsNotNone(added)
        assert added is not None
        self.assertEqual(added.index, 0)
        self.assertEqual(seq.tracks[1].id, t1_id)
        self.assertEqual(len(added.clips), 0)

    def test_add_track_at_cap(self) -> None:
        seq = self._seq(60)
        while len(seq.tracks) < MAX_TRACKS:
            self.assertIsNotNone(seq.add_track(len(seq.tracks) - 1))
        before = len(seq.tracks)
        self.assertIsNone(seq.add_track(0))
        self.assertEqual(len(seq.tracks), before)

    def test_delete_track_and_renumber(self) -> None:
        seq = self._seq(100)
        seq.add_track(0)
        self.assertTrue(seq.delete_track(1))
        self.assertEqual(len(seq.tracks), 2)
        self.assertEqual(seq.tracks[0].index, 0)
        self.assertEqual(seq.tracks[1].index, 1)

    def test_delete_last_track_refused(self) -> None:
        seq = self._seq(40)
        seq.tracks[1].clips.clear()
        self.assertTrue(seq.delete_track(1))
        self.assertFalse(seq.delete_track(0))
        self.assertEqual(len(seq.tracks), 1)

    def test_delete_selected_track_selection(self) -> None:
        seq = self._seq(80)
        seq.add_track(0)
        keep_id = seq.tracks[2].id
        seq.selected_track = 2
        self.assertTrue(seq.delete_track(0))
        self.assertEqual(seq.tracks[seq.selected_track].id, keep_id)

    def test_from_opened_media_track_count(self) -> None:
        one = Sequence.from_opened_media("/tmp/a.mp4", 30, track_count=1)
        self.assertEqual(len(one.tracks), 1)
        self.assertEqual(len(one.tracks[0].clips), 1)
        four = Sequence.from_opened_media("/tmp/b.mp4", 30, track_count=4)
        self.assertEqual(len(four.tracks), 4)
        self.assertEqual(len(four.tracks[0].clips), 1)
        self.assertEqual(len(four.tracks[1].clips), 1)
        self.assertEqual(four.tracks[2].clips, [])
        self.assertEqual(four.tracks[3].clips, [])
        clamped = Sequence.from_opened_media("/tmp/c.mp4", 30, track_count=99)
        self.assertEqual(len(clamped.tracks), MAX_TRACKS)

    def test_playback_span_after_delete_tail_track(self) -> None:
        seq = self._seq(100)
        seq.tracks[1].clips[0].out_frame = 49
        span = seq.sequence_playback_span()
        assert span is not None
        self.assertTrue(seq.delete_track(1))
        self.assertIsNotNone(seq.sequence_playback_span())
        self.assertLessEqual(seq.sequence_playback_span()[1], span[1])


if __name__ == "__main__":
    unittest.main()
