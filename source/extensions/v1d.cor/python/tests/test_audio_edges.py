# SPDX-License-Identifier: MIT
"""Audio follows transport edges only."""

from __future__ import annotations

import sys
import types
import unittest

if "carb" not in sys.modules:
    _carb = types.ModuleType("carb")
    _carb.log_warn = lambda _msg: None
    sys.modules["carb"] = _carb

from v1d.ngn.session import ScrubSession


class _FakeEngine:
    def request_frame(self, frame: int) -> None:
        self.frame = frame

    def set_scrubbing(self, on: bool) -> None:
        return None

    def set_playback(self, on: bool) -> None:
        return None

    def shutdown(self) -> None:
        return None


class _FakeAudio:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    def open(self, path: str) -> None:
        self.events.append(("open", path))

    def play_at(self, seconds: float) -> None:
        self.events.append(("play", seconds))

    def pause(self) -> None:
        self.events.append(("pause",))

    def close(self) -> None:
        self.events.append(("close",))


class TestAudioEdges(unittest.TestCase):
    def setUp(self) -> None:
        ScrubSession._instance = None
        self.session = ScrubSession()
        self.session._engine = _FakeEngine()
        self.session._clip_info = {"frames": 300, "fps_num": 30, "fps_den": 1}
        self.session._clip_path = "/clip.mp4"
        self.audio = _FakeAudio()
        self.session._audio = self.audio

    def test_forward_play_and_stop(self) -> None:
        self.session._last_request = 30
        self.session.transport_play(1, now=0.0)
        self.session.transport_stop()
        self.assertEqual(self.audio.events, [("play", 1.0), ("pause",)])

    def test_reverse_pauses(self) -> None:
        self.session.transport_play(-1, now=0.0)
        self.assertEqual(self.audio.events, [("pause",)])

    def test_scrub_begin_pauses(self) -> None:
        self.session.transport_play(1, now=0.0)
        self.audio.events.clear()
        self.session.on_slider_begin()
        self.assertEqual(self.audio.events, [("pause",)])

    def test_shutdown_closes(self) -> None:
        self.session.shutdown()
        self.assertIn(("close",), self.audio.events)
