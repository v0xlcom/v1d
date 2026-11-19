# SPDX-License-Identifier: MIT
"""A0: carb.audio create_sound_from_file(streaming) on the open MP4 path."""

from __future__ import annotations

import time

import carb
import carb.audio
import omni.ext
import omni.kit.app
import omni.kit.async_engine


class A0AudioSpikeExtension(omni.ext.IExt):
    def on_startup(self, ext_id: str) -> None:
        self._sub = None
        self._context = None
        self._sound = None
        self._voice = None
        self._t0 = 0.0
        omni.kit.async_engine.run_coroutine(self._run())

    def on_shutdown(self) -> None:
        if self._sub is not None:
            self._sub.unsubscribe()
            self._sub = None
        self._voice = None
        self._sound = None
        self._context = None

    async def _run(self) -> None:
        settings = carb.settings.get_settings()
        clip = str(settings.get("/exts/a0_audio_ext/clip") or "").strip()
        play_s = float(settings.get("/exts/a0_audio_ext/play_seconds") or 5.0)
        if not clip:
            carb.log_error("[A0] missing /exts/a0_audio_ext/clip")
            omni.kit.app.get_app().post_quit(1)
            return

        await omni.kit.app.get_app().next_update_async()

        data = carb.audio.acquire_data_interface()
        playback = carb.audio.acquire_playback_interface()
        carb.log_warn(f"[A0] create_sound_from_file streaming=True path={clip}")
        sound = data.create_sound_from_file(clip, streaming=True)
        if sound is None:
            carb.log_error("[A0] FAIL create_sound_from_file returned None")
            omni.kit.app.get_app().post_quit(1)
            return

        self._context = playback.create_context()
        if self._context is None:
            carb.log_error("[A0] FAIL create_context returned None")
            omni.kit.app.get_app().post_quit(1)
            return

        self._sound = sound
        self._voice = self._context.play_sound(sound)
        if self._voice is None:
            carb.log_error("[A0] FAIL play_sound returned None (decode/open?)")
            omni.kit.app.get_app().post_quit(1)
            return

        carb.log_warn("[A0] play_sound started; listening for is_playing")
        self._t0 = time.perf_counter()
        stream = omni.kit.app.get_app().get_update_event_stream()
        self._sub = stream.create_subscription_to_pop(self._on_update, name="a0_audio_spike")

        # Fail if playback never starts.
        for _ in range(120):
            await omni.kit.app.get_app().next_update_async()
            if self._voice and self._voice.is_playing():
                carb.log_warn("[A0] voice is_playing=True")
                return
        carb.log_error("[A0] FAIL voice never entered is_playing within ~2s")
        omni.kit.app.get_app().post_quit(1)

    def _on_update(self, _event) -> None:
        if self._context is not None:
            self._context.update()
        settings = carb.settings.get_settings()
        play_s = float(settings.get("/exts/a0_audio_ext/play_seconds") or 5.0)
        if time.perf_counter() - self._t0 < play_s:
            return
        playing = self._voice.is_playing() if self._voice else False
        carb.log_warn(f"[A0] PASS played {play_s:.1f}s is_playing={playing}")
        omni.kit.app.get_app().post_quit(0)
