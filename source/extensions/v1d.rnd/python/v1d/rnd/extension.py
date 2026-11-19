# SPDX-License-Identifier: MIT
"""Render composition to MP4 (NVENC via ffmpeg; frames from GPU engine)."""

from __future__ import annotations

import threading

import carb
import omni.ext
import omni.kit.app
import omni.ui as ui
from omni.kit.menu.utils import MenuHelperExtension

from v1d.kit import dialogs, project_hooks
from v1d.kit.window_menu import unwire_window_menu, wire_window_menu
from v1d.ngn.session import ScrubSession
from v1d.rnd.options import RenderOptions, load_options, save_options
from v1d.rnd.render_job import RenderProgress, run_render

WINDOW_TITLE = "Render"


class V1dRenderExtension(omni.ext.IExt, MenuHelperExtension):
    def on_startup(self, ext_id: str) -> None:
        self._closed = False
        settings = carb.settings.get_settings()
        title = str(settings.get("/exts/v1d.rnd/window_title") or WINDOW_TITLE)
        self._session = ScrubSession.get()
        self._cancel = [False]
        self._worker: threading.Thread | None = None

        saved = load_options()
        self._window = ui.Window(title, width=520, height=420)
        with self._window.frame:
            with ui.VStack(spacing=6):
                self._folder = ui.StringField()
                self._folder.model.set_value(saved.folder)
                ui.Button("Browse folder…", clicked_fn=self._pick_folder)
                self._name = ui.StringField()
                self._name.model.set_value(saved.filename)
                self._fps = ui.FloatField()
                self._fps.model.set_value(float(saved.fps))
                with ui.HStack():
                    ui.Button("Render", clicked_fn=self._start)
                    ui.Button("Cancel", clicked_fn=self._cancel_render)
                self._progress = ui.Label("Idle")
                self._status = ui.Label("")

        self._window.visible = False
        self._window_title = title
        wire_window_menu(self, title, self._window, self._show_window)
        project_hooks.register("show_render", self._menu_show)

        stream = omni.kit.app.get_app().get_update_event_stream()
        self._sub = stream.create_subscription_to_pop(self._on_update, name="v1d.rnd")

    def _show_window(self, visible: bool) -> None:
        self._window.visible = bool(visible)

    def _menu_show(self) -> None:
        self._show_window(True)

    def _pick_folder(self) -> None:
        path = dialogs.pick_folder()
        if path:
            self._folder.model.set_value(path)

    def _options_from_ui(self) -> RenderOptions:
        # No widgets for codec, size, CQ, or overwrite yet. Validate even defaults
        # and refuse an existing file. run_render still chooses the PNG size.
        name = self._name.model.get_value_as_string().strip() or "v1d_render.mp4"
        return RenderOptions(
            folder=self._folder.model.get_value_as_string().strip(),
            filename=name,
            codec="h264",
            width=1920,
            height=1080,
            fps=float(self._fps.model.get_value_as_float()),
            cq=23,
            overwrite=False,
        )

    def _start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            self._status.text = "Render already running"
            return
        opts = self._options_from_ui()
        err = opts.validate()
        if err:
            self._status.text = err
            return
        save_options(opts)
        out = opts.output_path()
        fps = float(opts.fps)
        self._cancel[0] = False
        self._progress.text = "Starting…"

        def work() -> None:
            def prog(p: RenderProgress) -> None:
                self._progress.text = f"{p.frames_done}/{p.frames_total}  {p.fps:.1f} fps"

            ok, msg = run_render(out, fps, cancel_flag=self._cancel, progress_cb=prog)
            self._last_msg = (ok, msg)

        self._worker = threading.Thread(target=work, name="v1d.rnd.worker", daemon=True)
        self._worker.start()

    def _cancel_render(self) -> None:
        self._cancel[0] = True

    def _on_update(self, _e) -> None:
        if self._closed:
            return
        if self._worker is not None and not self._worker.is_alive():
            self._worker = None
            ok, msg = getattr(self, "_last_msg", (False, ""))
            if ok:
                self._status.text = f"Done: {msg}"
                self._progress.text = "Idle"
            else:
                self._status.text = msg
                self._progress.text = "Failed"

    def on_shutdown(self) -> None:
        self._closed = True
        self._cancel[0] = True
        project_hooks.unregister("show_render")
        self._sub = None
        if hasattr(self, "_window"):
            unwire_window_menu(self, getattr(self, "_window_title", WINDOW_TITLE))