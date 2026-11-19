# SPDX-License-Identifier: MIT
"""ScrubSession listener lifecycle (PLAN_03)."""

from __future__ import annotations

import sys
import types
import unittest

if "carb" not in sys.modules:
    _carb = types.ModuleType("carb")
    _carb.log_warn = lambda _msg: None
    sys.modules["carb"] = _carb

from v1d.ngn.session import ScrubSession


class TestSessionListeners(unittest.TestCase):
    def setUp(self) -> None:
        ScrubSession._instance = None
        self.session = ScrubSession()

    def tearDown(self) -> None:
        ScrubSession._instance = None

    def test_frame_listener_add_remove(self) -> None:
        seen: list[int] = []

        def on_frame(n: int) -> None:
            seen.append(n)

        self.session.add_frame_listener(on_frame)
        self.session._emit_frame(1)
        self.assertEqual(seen, [1])
        self.session.remove_frame_listener(on_frame)
        self.session._emit_frame(2)
        self.assertEqual(seen, [1])

    def test_bad_frame_listener_dropped(self) -> None:
        good: list[int] = []

        def bad(_n: int) -> None:
            raise AttributeError("_status")

        def good_fn(n: int) -> None:
            good.append(n)

        self.session.add_frame_listener(bad)
        self.session.add_frame_listener(good_fn)
        self.session._emit_frame(0)
        self.assertEqual(good, [0])
        self.session._emit_frame(1)
        self.assertEqual(good, [0, 1])
        self.assertEqual(len(self.session._frame_listeners), 1)

    def test_clear_listeners_on_shutdown_without_engine(self) -> None:
        calls: list[str] = []
        self.session.add_clip_path_listener(lambda p: calls.append(p))
        self.session.shutdown()
        self.assertIsNone(ScrubSession._instance)
        self.session._emit_clip_path("/tmp/x")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
