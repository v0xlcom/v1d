# SPDX-License-Identifier: MIT
"""Preview window, engine session host, S2 bench, C10 selftest."""

from __future__ import annotations

import pathlib
import time

import carb
import omni.ext
import omni.kit.app
import omni.ui as ui
from omni.kit.menu.utils import MenuHelperExtension

from v1d.ngn import _scrub
from v1d.ngn.paths import default_fatbin
from v1d.ngn.session import ScrubSession
from v1d.kit.square_menu import install_default_square_ticks
from v1d.kit.window_menu import unwire_window_menu, wire_window_menu
from v1d.kit.window_title import apply_window_title
from v1d.pv.selftest_runner import KitSelftestRunner
from v1d.pv.ui import menu_bar, workspace_layout

WINDOW_TITLE = "Preview"


def _percentile(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    s = sorted(samples)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


class V1dPreviewExtension(omni.ext.IExt, MenuHelperExtension):
    def on_startup(self, ext_id: str):
        install_default_square_ticks()
        settings = carb.settings.get_settings()
        self._fatbin = str(default_fatbin())
        self._device = int(settings.get("/exts/v1d.cor/cuda_device") or 0)
        self._cache_mb = int(settings.get("/exts/v1d.cor/cache_vram_mb") or 0)
        self._s2 = bool(settings.get("/exts/v1d.pv/s2_bench"))
        self._selftest = bool(settings.get("/exts/v1d.pv/selftest"))
        self._a0_audio = bool(settings.get("/exts/v1d.pv/a0_audio_spike"))
        self._a0_runner = None
        clip = str(settings.get("/exts/v1d.cor/clip") or "").strip()

        apply_window_title()

        if self._a0_audio:
            spike_clip = str(settings.get("/exts/v1d.pv/a0_audio_spike_clip") or clip).strip()
            if not spike_clip:
                carb.log_error("[A0] set /exts/v1d.pv/a0_audio_spike_clip (or /exts/v1d.cor/clip)")
                omni.kit.app.get_app().post_quit(1)
                return
            from v1d.pv.a0_audio_spike import A0AudioSpikeRunner

            play_s = float(settings.get("/exts/v1d.pv/a0_audio_spike_seconds") or 5.0)
            self._a0_runner = A0AudioSpikeRunner(spike_clip, play_s)
            self._a0_runner.start()
            return

        if self._s2:
            self._startup_s2()
            return

        session = ScrubSession.get()

        if self._selftest:
            self._selftest_runner = KitSelftestRunner(session)
            stream = omni.kit.app.get_app().get_update_event_stream()
            self._sub = stream.create_subscription_to_pop(
                self._selftest_runner.on_update, name="v1d.pv.selftest"
            )
            return

        title = str(settings.get("/exts/v1d.pv/window_title") or WINDOW_TITLE)
        self._provider = ui.ByteImageProvider()
        self._window = ui.Window(title, width=960, height=540)
        with self._window.frame:
            ui.ImageWithProvider(self._provider, width=ui.Fraction(1), height=ui.Fraction(1))

        self._window_title = title
        wire_window_menu(self, title, self._window, self._show_window)
        menu_bar.install_file_menu()
        menu_bar.install_layout_menu()
        menu_bar.install_power_menu()
        menu_bar.install_reload_button(self._on_reload)
        workspace_layout.schedule_layout()

        self._session = session
        self._polling = True
        self._gap_cleared = False
        session.add_blank_listener(self._on_blank_preview)
        stream = omni.kit.app.get_app().get_update_event_stream()
        self._sub = stream.create_subscription_to_pop(self._on_update, name="v1d.pv")

    def _on_blank_preview(self) -> None:
        """Ask the next update to show black."""
        self._gap_cleared = False

    def _startup_s2(self) -> None:
        _scrub.cuda_init(self._device, self._fatbin)
        self._provider = ui.ByteImageProvider()
        self._window = ui.Window("v1d S2", width=800, height=600)
        with self._window.frame:
            ui.ImageWithProvider(self._provider, width=ui.Fraction(1), height=ui.Fraction(1))
        self._sizes = [(1280, 720), (3840, 2160)]
        self._size_idx = 0
        self._ptr = 0
        self._stride = 0
        self._w = 0
        self._h = 0
        self._frame = 0
        self._warmup_left = 30
        self._samples: list[float] = []
        self._results: dict[str, dict[str, float]] = {}
        self._alloc_for_size(self._sizes[0])
        stream = omni.kit.app.get_app().get_update_event_stream()
        self._sub = stream.create_subscription_to_pop(self._on_update_s2, name="v1d.pv.s2")

    def _show_window(self, visible: bool) -> None:
        self._window.visible = bool(visible)

    def _on_reload(self) -> None:
        from v1d.pv.ui.reload import request_reload  # noqa: PLC0415

        clip = str(carb.settings.get_settings().get("/exts/v1d.cor/clip") or "")
        if not request_reload(clip):
            carb.log_warn("[v1d.pv] Reload spawn failed")

    def _on_update(self, _e) -> None:
        if not getattr(self, "_polling", False):
            return
        session = self._session
        if not session.active:
            return
        session.tick_playback(lambda: session.last_request)
        if session.preview_gap:
            if not self._gap_cleared:
                self._provider.set_bytes_data([0, 0, 0, 255], [1, 1])
                self._gap_cleared = True
            return
        self._gap_cleared = False
        frame = session.poll_frame()
        if frame is not None:
            self._provider.set_bytes_data_from_gpu(
                int(frame["ptr"]), [frame["width"], frame["height"]]
            )

    def _alloc_for_size(self, wh: tuple[int, int]) -> None:
        if self._ptr:
            _scrub.cuda_free(self._ptr)
        self._w, self._h = wh
        self._ptr, self._stride = _scrub.cuda_alloc_rgba(self._w, self._h)
        self._frame = 0
        self._warmup_left = 30
        self._samples = []

    def _bench_upload(self) -> float:
        _scrub.cuda_fill_rgba_frame(self._ptr, self._w, self._h, self._stride, self._frame)
        t0 = time.perf_counter()
        self._provider.set_bytes_data_from_gpu(int(self._ptr), [self._w, self._h])
        return (time.perf_counter() - t0) * 1000.0

    def _on_update_s2(self, _e) -> None:
        self._frame += 1
        ms = self._bench_upload()
        if self._warmup_left > 0:
            self._warmup_left -= 1
            return
        self._samples.append(ms)
        if len(self._samples) < 400:
            return
        p50 = _percentile(self._samples, 0.50)
        p95 = _percentile(self._samples, 0.95)
        tag = f"{self._w}x{self._h}"
        self._results[tag] = {"p50_ms": p50, "p95_ms": p95}
        carb.log_warn(f"[v1d.pv S2] {tag} p50={p50:.3f} p95={p95:.3f}")
        self._size_idx += 1
        if self._size_idx < len(self._sizes):
            self._alloc_for_size(self._sizes[self._size_idx])
            return
        gate_720 = self._results["1280x720"]["p95_ms"] <= 3.0
        gate_4k = self._results["3840x2160"]["p95_ms"] <= 8.0
        carb.log_warn(f"[v1d.pv S2] GATE p95_720<=3ms: {gate_720} p95_4k<=8ms: {gate_4k}")
        omni.kit.app.get_app().post_quit(0 if (gate_720 and gate_4k) else 1)

    def on_shutdown(self) -> None:
        if getattr(self, "_a0_runner", None):
            self._a0_runner.shutdown()
            return
        self._polling = False
        session = getattr(self, "_session", None)
        if session is not None:
            session.remove_blank_listener(self._on_blank_preview)
        if getattr(self, "_window", None):
            if not getattr(self, "_s2", False) and not getattr(self, "_selftest", False):
                unwire_window_menu(self, getattr(self, "_window_title", WINDOW_TITLE))
                menu_bar.remove_file_menu()
                menu_bar.remove_layout_menu()
                menu_bar.remove_power_menu()
                menu_bar.remove_reload_button()
                workspace_layout.save_workspace()
            self._window.visible = False
        if getattr(self, "_s2", False) and getattr(self, "_ptr", 0):
            _scrub.cuda_free(self._ptr)
            _scrub.cuda_shutdown()
        self._sub = None
