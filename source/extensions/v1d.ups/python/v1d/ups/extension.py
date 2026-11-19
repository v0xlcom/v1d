# SPDX-License-Identifier: MIT
"""Upscaler window — snapshot preview frame, external upscale, wipe compare."""

from __future__ import annotations

import tempfile
import threading

import carb
import omni.ext
import omni.kit.app
import omni.ui as ui
from omni.kit.menu.utils import MenuHelperExtension

from v1d.kit.window_menu import unwire_window_menu, wire_window_menu
from v1d.ngn import _scrub
from v1d.ngn.session import ScrubSession
from v1d.ups.run import UpscaleResult, upscale_png_bytes
from v1d.ups.wipe import WipeCompare, downscale_rgba_nn

WINDOW_TITLE = "Upscaler"

ENGINE_CHOICES: list[tuple[str, str]] = [
    ("seedvr2", "SeedVR2"),
    ("flashvsr", "FlashVSR"),
    ("realesrgan", "Real-ESRGAN"),
    ("realcugan", "Real-CUGAN"),
    ("video2x", "Video2X (Anime4K)"),
    ("rve", "REAL Video Enhancer"),
]


class V1dUpscalerExtension(omni.ext.IExt, MenuHelperExtension):
    def on_startup(self, ext_id: str) -> None:
        self._closed = False
        settings = carb.settings.get_settings()
        title = str(settings.get("/exts/v1d.ups/window_title") or WINDOW_TITLE)
        self._root = str(settings.get("/exts/v1d.ups/root") or "../v1d_ups")
        self._session = ScrubSession.get()
        self._snapshot_ptr = 0
        self._snapshot_stride = 0
        self._worker: threading.Thread | None = None
        self._pending: UpscaleResult | None = None
        self._pending_label = ""
        self._snap_w = 0
        self._snap_h = 0
        self._up_tex_ptr = 0

        self._window = ui.Window(title, width=720, height=560)
        with self._window.frame:
            with ui.VStack(spacing=6):
                labels = [label for _eid, label in ENGINE_CHOICES]
                self._combo = ui.ComboBox(2, *labels, width=ui.Fraction(1))
                ui.Button("Upscale frame", clicked_fn=self._on_upscale_clicked)
                self._status = ui.Label("Open a clip and wait for a frame")
                self._wipe = WipeCompare(height=420)

        self._window_title = title
        wire_window_menu(self, title, self._window, self._show_window)

        stream = omni.kit.app.get_app().get_update_event_stream()
        self._sub = stream.create_subscription_to_pop(self._on_update, name="v1d.ups")

    def _show_window(self, visible: bool) -> None:
        self._window.visible = bool(visible)

    def _engine_id(self) -> str:
        idx = int(self._combo.model.get_item_value_model().get_value_as_int())
        if idx < 0 or idx >= len(ENGINE_CHOICES):
            return "realesrgan"
        return ENGINE_CHOICES[idx][0]

    def _on_upscale_clicked(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            self._status.text = "Upscale already running"
            return
        latest = self._session.latest_present()
        if not latest:
            self._status.text = "Open a clip and wait for a frame"
            return
        w, h = int(latest["width"]), int(latest["height"])
        self._snap_w, self._snap_h = w, h
        if self._snapshot_ptr:
            _scrub.cuda_free(self._snapshot_ptr)
        self._snapshot_ptr, self._snapshot_stride = _scrub.cuda_alloc_rgba(w, h)
        if not self._session.copy_latest_rgba_to(self._snapshot_ptr, self._snapshot_stride):
            self._status.text = "Snapshot copy failed"
            return
        self._wipe.set_original_gpu(self._snapshot_ptr, w, h)
        engine_id = self._engine_id()
        label = next((lb for eid, lb in ENGINE_CHOICES if eid == engine_id), engine_id)
        self._status.text = f"Upscaling with {label}…"
        try:
            rgba = _scrub.cuda_read_rgba(
                int(self._snapshot_ptr), w, h, int(self._snapshot_stride)
            )
        except Exception as exc:  # noqa: BLE001
            carb.log_error(f"[v1d.ups] snapshot read: {exc}")
            self._status.text = f"Snapshot read failed: {exc}"
            return
        work = tempfile.mkdtemp(prefix="v1d_ups_")
        self._pending_label = label
        root = self._root
        snap_stride = int(self._snapshot_stride)

        def work_fn() -> None:
            try:
                self._pending = upscale_png_bytes(
                    root, engine_id, w, h, rgba, snap_stride, work, timeout_s=600.0
                )
            except Exception as exc:  # noqa: BLE001
                self._pending = UpscaleResult(False, 0.0, error=str(exc))

        self._worker = threading.Thread(target=work_fn, name="v1d.ups.worker", daemon=True)
        self._worker.start()

    def _on_update(self, _e) -> None:
        if self._closed:
            return
        if self._worker is not None and not self._worker.is_alive():
            self._worker = None
            res = self._pending
            self._pending = None
            if res is None:
                return
            if not res.ok:
                self._status.text = f"{self._pending_label}: {res.error}"
                return
            cw, ch = self._snap_w, self._snap_h
            if cw <= 0 or ch <= 0:
                cw, ch = res.out_w, res.out_h
            try:
                tex = downscale_rgba_nn(res.rgba, res.out_w, res.out_h, cw, ch)
                if self._up_tex_ptr:
                    _scrub.cuda_free(self._up_tex_ptr)
                self._up_tex_ptr, up_stride = _scrub.cuda_alloc_rgba(cw, ch)
                _scrub.cuda_write_rgba(
                    int(self._up_tex_ptr), cw, ch, int(up_stride), tex
                )
                self._wipe.set_upscaled_gpu(self._up_tex_ptr, cw, ch, int(up_stride))
            except Exception as exc:  # noqa: BLE001
                carb.log_error(f"[v1d.ups] upscale display upload: {exc}")
                self._status.text = f"{self._pending_label}: display upload failed"
                return
            self._status.text = (
                f"{self._pending_label} — {res.out_w}×{res.out_h} in {res.wall_s:.1f}s"
            )

    def on_shutdown(self) -> None:
        self._closed = True
        if self._snapshot_ptr:
            _scrub.cuda_free(self._snapshot_ptr)
            self._snapshot_ptr = 0
        if self._up_tex_ptr:
            _scrub.cuda_free(self._up_tex_ptr)
            self._up_tex_ptr = 0
        if getattr(self, "_window", None):
            unwire_window_menu(self, getattr(self, "_window_title", WINDOW_TITLE))
            self._window.visible = False
        self._sub = None
