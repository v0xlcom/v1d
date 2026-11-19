# SPDX-License-Identifier: MIT
"""PLAN_07 A0: carb.audio streaming from open MP4 (dev spike; enable via settings)."""

from __future__ import annotations

import time

import carb
import carb.audio
import omni.kit.app
import omni.kit.async_engine


class A0AudioSpikeRunner:
    def __init__(self, clip: str, play_seconds: float) -> None:
        self._clip = clip
        self._play_seconds = play_seconds
        self._sub = None
        self._context = None
        self._voice = None
        self._t0 = 0.0

    def start(self) -> None:
        omni.kit.async_engine.run_coroutine(self._run())

    def shutdown(self) -> None:
        if self._sub is not None:
            self._sub.unsubscribe()
            self._sub = None
        self._voice = None
        self._context = None

    async def _run(self) -> None:
        await omni.kit.app.get_app().next_update_async()
        data = carb.audio.acquire_data_interface()
        playback = carb.audio.acquire_playback_interface()
        carb.log_warn(f"[A0] create_sound_from_file streaming=True path={self._clip}")
        try:
            sound = data.create_sound_from_file(self._clip, streaming=True)
        except Exception as exc:  # noqa: BLE001
            carb.log_error(f"[A0] FAIL create_sound_from_file raised: {exc}")
            omni.kit.app.get_app().post_quit(1)
            return
        if sound is None:
            carb.log_error("[A0] FAIL create_sound_from_file returned None")
            omni.kit.app.get_app().post_quit(1)
            return

        self._context = playback.create_context()
        if self._context is None:
            carb.log_error("[A0] FAIL create_context returned None")
            omni.kit.app.get_app().post_quit(1)
            return

        self._voice = self._context.play_sound(sound)
        if self._voice is None:
            carb.log_error("[A0] FAIL play_sound returned None (decode/open?)")
            omni.kit.app.get_app().post_quit(1)
            return

        self._t0 = time.perf_counter()
        stream = omni.kit.app.get_app().get_update_event_stream()
        self._sub = stream.create_subscription_to_pop(self._on_update, name="v1d.pv.a0_audio")

        for _ in range(120):
            await omni.kit.app.get_app().next_update_async()
            if self._voice.is_playing():
                carb.log_warn("[A0] voice is_playing=True")
                return
        carb.log_error("[A0] FAIL voice never entered is_playing within ~2s")
        omni.kit.app.get_app().post_quit(1)

    def _on_update(self, _event) -> None:
        if self._context is not None:
            self._context.update()
        if time.perf_counter() - self._t0 < self._play_seconds:
            return
        playing = self._voice.is_playing() if self._voice else False
        carb.log_warn(f"[A0] PASS played {self._play_seconds:.1f}s is_playing={playing}")
        omni.kit.app.get_app().post_quit(0)
