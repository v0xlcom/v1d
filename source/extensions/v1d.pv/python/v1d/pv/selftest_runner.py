# SPDX-License-Identifier: MIT
"""C10 Kit selftest (engine-only sweep)."""

from __future__ import annotations

import random
import time

import carb

from v1d.ngn.session import ScrubSession


class KitSelftestRunner:
    def __init__(self, session: ScrubSession) -> None:
        self._session = session
        self._engine = session.engine
        self._clip_info = session.clip_info
        if not self._clip_info:
            raise RuntimeError("selftest requires an open clip")
        self._t0 = time.perf_counter()
        self._done = False
        self._random_left = 20
        random.seed(0)
        self._last_request = 0

    def on_update(self, _e) -> None:
        if self._done:
            return
        n = int(self._clip_info["frames"])
        elapsed = time.perf_counter() - self._t0
        if elapsed < 5.0:
            target = int((elapsed / 5.0) * (n - 1))
            self._engine.set_scrubbing(True)
            self._last_request = target
            self._engine.request_frame(target)
            return
        if self._random_left > 0:
            target = random.randrange(n)
            self._engine.set_scrubbing(True)
            self._last_request = target
            self._engine.request_frame(target)
            self._random_left -= 1
            return
        self._engine.set_scrubbing(False)
        self._engine.request_frame(self._last_request)
        self._done = True
        frame = None
        for _ in range(500):
            frame = self._engine.poll()
            if frame and frame["frame"] == self._last_request and frame["tier"] == "exact":
                break
            time.sleep(0.01)
        ok = frame is not None and frame["frame"] == self._last_request and frame["tier"] == "exact"
        carb.log_warn(f"[v1d.pv selftest] pass={ok} last={self._last_request} got={frame}")
        import omni.kit.app  # noqa: PLC0415

        omni.kit.app.get_app().post_quit(0 if ok else 1)
