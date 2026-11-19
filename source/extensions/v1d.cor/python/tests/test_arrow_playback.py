# SPDX-License-Identifier: MIT
"""Timeline arrow shuttle (PLAN_04_TL_SLIDER)."""

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


class TestArrowShuttle(unittest.TestCase):
    def setUp(self) -> None:
        ScrubSession._instance = None
        self.session = ScrubSession()
        self.engine = _FakeEngine()
        self.session._engine = self.engine
        self.session._clip_info = {
            "frames": 100,
            "fps_num": 30,
            "fps_den": 1,
            "width": 192,
            "height": 108,
        }
        self.session._last_request = 10

    def tearDown(self) -> None:
        ScrubSession._instance = None

    def test_right_tap_scrub_then_exact_on_release(self) -> None:
        t0 = 1000.0
        self.assertTrue(self.session.on_arrow_pressed(1, 10))
        self.assertTrue(self.session.on_arrow_pressed(1, 10))
        self.session.on_arrow_released(1)
        self.assertEqual(self.session.last_request, 11)
        self.assertEqual(self.session.play_dir, 0)
        self.assertIn(True, self.engine.scrubbing)
        self.assertIn(False, self.engine.scrubbing)

    def test_left_tap(self) -> None:
        self.session.on_arrow_pressed(-1, 10)
        self.session.on_arrow_released(-1)
        self.assertEqual(self.session.last_request, 9)

    def test_at_end_and_start_unchanged(self) -> None:
        self.session._last_request = 99
        self.assertFalse(self.session.on_arrow_pressed(1, 99))
        self.session._last_request = 0
        self.assertFalse(self.session.on_arrow_pressed(-1, 0))

    def test_opposite_key_steps_once(self) -> None:
        self.session.on_arrow_pressed(1, 5)
        self.assertEqual(self.session.last_request, 6)
        self.session.on_arrow_pressed(-1, 6)
        self.session.on_arrow_released(-1)
        self.assertEqual(self.session.last_request, 5)

    def test_hold_forward_one_second(self) -> None:
        t0 = 1000.0
        self.session.on_arrow_pressed(1, 10, now=t0)
        self.assertEqual(self.session.last_request, 11)
        self.session.tick_playback(now=t0 + ARROW_HOLD_S + 0.01)
        self.assertEqual(self.session.play_dir, 1)
        self.session.tick_playback(now=t0 + ARROW_HOLD_S + 1.0)
        self.assertEqual(self.session.last_request, 41)

    def test_hold_left_one_second(self) -> None:
        t0 = 2000.0
        self.session.on_arrow_pressed(-1, 50, now=t0)
        self.assertEqual(self.session.last_request, 49)
        self.session.tick_playback(now=t0 + ARROW_HOLD_S + 0.01)
        self.assertEqual(self.session.play_dir, -1)
        self.session.tick_playback(now=t0 + ARROW_HOLD_S + 1.0)
        self.assertEqual(self.session.last_request, 19)

    def test_release_during_play_no_extra_step(self) -> None:
        t0 = 3000.0
        self.session.on_arrow_pressed(1, 10, now=t0)
        self.session.tick_playback(now=t0 + ARROW_HOLD_S + 0.5)
        idx = self.session.last_request
        self.session.on_arrow_released(1)
        self.assertEqual(self.session.last_request, idx)
        self.assertEqual(self.session.play_dir, 0)

    def test_step_frame_plus_one(self) -> None:
        self.session._last_request = 10
        self.session.step_frame(1)
        self.assertEqual(self.session.last_request, 11)
        self.assertEqual(self.session.play_dir, 0)
        self.assertIn(False, self.engine.scrubbing)

    def test_step_frame_at_max_no_request(self) -> None:
        self.session._last_request = 99
        before = len(self.engine.frames)
        self.session.step_frame(1)
        self.assertEqual(len(self.engine.frames), before)

    def test_transport_play_forward_one_second(self) -> None:
        t0 = 5000.0
        self.session._last_request = 10
        self.session.transport_play(1, now=t0)
        self.assertEqual(self.session.play_dir, 1)
        self.assertTrue(self.engine.playback)
        self.assertIn(True, self.engine.scrubbing)
        self.session.tick_playback(now=t0 + 1.0)
        self.assertEqual(self.session.last_request, 40)

    def test_transport_play_reverse_one_second(self) -> None:
        t0 = 6000.0
        self.session._last_request = 50
        self.session.transport_play(-1, now=t0)
        self.session.tick_playback(now=t0 + 1.0)
        self.assertEqual(self.session.last_request, 20)

    def test_transport_stop_keeps_index(self) -> None:
        t0 = 7000.0
        self.session._last_request = 10
        self.session.transport_play(1, now=t0)
        self.session.tick_playback(now=t0 + 0.5)
        idx = self.session.last_request
        self.session.transport_stop()
        self.assertEqual(self.session.last_request, idx)
        self.assertEqual(self.session.play_dir, 0)
        self.assertIn(False, self.engine.scrubbing)

    def test_reverse_play_reaches_frame_zero(self) -> None:
        t0 = 9000.0
        self.session._last_request = 2
        self.session.transport_play(-1, now=t0)
        self.session.tick_playback(now=t0 + 1.0)
        self.assertEqual(self.session.last_request, 0)
        self.assertIn(1, self.engine.frames)
        self.assertEqual(self.engine.frames[-1], 0)
        self.assertEqual(self.session.play_dir, 0)

    def test_left_hold_reaches_frame_zero(self) -> None:
        t0 = 9100.0
        self.session.on_arrow_pressed(-1, 3, now=t0)
        self.assertEqual(self.session.last_request, 2)
        self.session.tick_playback(now=t0 + ARROW_HOLD_S + 1.0)
        self.assertEqual(self.session.last_request, 0)
        self.assertIn(1, self.engine.frames)
        self.assertEqual(self.session.play_dir, 0)

    def test_forward_play_reaches_frame_599(self) -> None:
        t0 = 9300.0
        self.session._clip_info["frames"] = 600
        self.session._last_request = 590
        self.session.transport_play(1, now=t0)
        self.session.tick_playback(now=t0 + 1.0)
        self.assertEqual(self.session.last_request, 599)
        self.assertEqual(self.session.play_dir, 0)
        self.session.tick_playback(now=t0 + 1.1)

    def test_forward_play_reaches_last_frame(self) -> None:
        t0 = 9200.0
        self.session._last_request = 97
        self.session.transport_play(1, now=t0)
        self.session.tick_playback(now=t0 + 1.0)
        self.assertEqual(self.session.last_request, 99)
        self.assertEqual(self.session.play_dir, 0)

    def test_step_frame_stops_play_first(self) -> None:
        t0 = 8000.0
        self.session._last_request = 10
        self.session.transport_play(1, now=t0)
        self.session.step_frame(1)
        self.assertEqual(self.session.last_request, 11)
        self.assertEqual(self.session.play_dir, 0)


if __name__ == "__main__":
    unittest.main()
