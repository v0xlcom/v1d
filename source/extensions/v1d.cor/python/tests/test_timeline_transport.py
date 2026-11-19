# SPDX-License-Identifier: MIT
"""Sequence-clock playback (PLAN_TWO_TRACKS)."""

from __future__ import annotations

import sys
import types
import unittest

if "carb" not in sys.modules:
    _carb = types.ModuleType("carb")
    _carb.log_warn = lambda _msg: None
    sys.modules["carb"] = _carb

from v1d.ngn.session import ARROW_HOLD_S, ScrubSession


class _FakeEngine:
    def __init__(self) -> None:
        self.frames: list[int] = []
        self.scrubbing: list[bool] = []

    def request_frame(self, frame: int) -> None:
        self.frames.append(frame)

    def set_scrubbing(self, on: bool) -> None:
        self.scrubbing.append(on)

    def set_playback(self, on: bool) -> None:
        self.playback = on


class TestTimelineTransport(unittest.TestCase):
    def setUp(self) -> None:
        ScrubSession._instance = None
        self.session = ScrubSession()
        self.engine = _FakeEngine()
        self.session._engine = self.engine
        self.session._clip_info = {
            "frames": 1000,
            "fps_num": 30,
            "fps_den": 1,
            "width": 192,
            "height": 108,
        }
        self.sequences: list[int] = []

        def source_at(seq: int) -> int | None:
            if 0 <= seq <= 226:
                return seq
            if 228 <= seq <= 300:
                return None
            if 301 <= seq <= 500:
                return seq
            return None

        self._source_at = source_at
        self.session.add_sequence_listener(lambda s: self.sequences.append(s))
        self.session.configure_timeline(0, 500, source_at)

    def tearDown(self) -> None:
        ScrubSession._instance = None

    def test_play_past_first_track_end(self) -> None:
        t0 = 2000.0
        self.session._last_request = 200
        self.session.transport_play(1, now=t0, origin_sequence=200)
        self.session.tick_playback(now=t0 + 5.0)
        self.assertGreater(max(self.sequences), 226)
        self.assertIn(301, self.engine.frames)

    def test_play_through_gap(self) -> None:
        t0 = 3000.0
        self.session.transport_play(1, now=t0, origin_sequence=220)
        self.session.tick_playback(now=t0 + 0.5)
        self.assertTrue(self.session.preview_gap)
        self.assertGreater(max(self.sequences), 228)

    def test_play_starts_in_gap(self) -> None:
        t0 = 4000.0
        self.session._preview_gap = True
        self.session.transport_play(1, now=t0, origin_sequence=229)
        self.session.tick_playback(now=t0 + 3.0)
        self.assertIn(301, self.sequences)

    def test_reverse_stops_at_span_lo(self) -> None:
        t0 = 5000.0
        self.session.transport_play(-1, now=t0, origin_sequence=10)
        self.session.tick_playback(now=t0 + 1.0)
        self.assertIn(0, self.sequences)
        self.assertEqual(self.session.play_dir, 0)

    def test_arrow_hold_crosses_handoff(self) -> None:
        t0 = 6000.0
        self.session.on_arrow_sequence_arm(1, 220, now=t0)
        self.session.tick_playback(now=t0 + ARROW_HOLD_S + 2.0)
        self.assertGreater(max(self.sequences), 226)


if __name__ == "__main__":
    unittest.main()
