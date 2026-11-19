# SPDX-License-Identifier: MIT
"""Console window toolbar tweaks (omni.kit.window.console)."""

from __future__ import annotations

import copy
from functools import partial

import carb
import carb.logging
import omni.kit.app
import omni.ui as ui
from omni.kit.window.console.scripts.console_toolbar import (
    ConsoleToolbar,
    SearchField,
    ToolbarButton,
)
from omni.kit.window.console.scripts.style import CONSOLE_WINDOW_STYLE

_CONSOLE_TITLE = "Console"
_LOG_PREFIX = "Console logs of v1d: "


def console_log_clipboard_text(body: str) -> str:
    """All console messages, prefixed for paste."""
    return f"{_LOG_PREFIX}{body or ''}"


def _copy_console_logs(self) -> None:
    import omni.kit.clipboard

    view = getattr(self._log_view, "_console_log_view", None)
    body = ""
    if view is not None:
        try:
            view.select_all_logs()
            body = view.get_selected_log_string() or ""
        except Exception as exc:  # noqa: BLE001
            carb.log_warn(f"[v1d.pv] copy console logs failed: {exc}")
            return
    omni.kit.clipboard.copy(console_log_clipboard_text(body))


def _fill_toolbar(self, show_instance_id_button: bool = False) -> None:
    """Icons and search on the left. Copy, then Clear Console, on the right."""
    show_open_log_buttons = carb.settings.get_settings().get(
        "/exts/omni.kit.window.console/showOpenLogButtons"
    )

    if show_instance_id_button:
        ToolbarButton("copy", "Copy Instance ID", self._copy_stream_id)

    try:
        import webbrowser

        webbrowser.get()
        ToolbarButton(
            "open_log",
            "Open Log File",
            self._open_log_file,
            visible=show_open_log_buttons,
        )
        ToolbarButton(
            "open_folder",
            "Open Log Folder",
            self._open_log_folder,
            visible=show_open_log_buttons,
        )
    except Exception:  # noqa: BLE001
        carb.log_verbose("webbrowser is not available, hide log file buttons")

    self._command_button = ToolbarButton(
        "command",
        "Enable Command Field",
        self._show_command_input,
        text=">_",
    )
    self._build_filter_button()
    self._log_buttons = [
        ToolbarButton(
            "verbose",
            "Verbose",
            partial(self._set_log_level, carb.logging.LEVEL_VERBOSE),
        ),
        ToolbarButton(
            "info",
            "Info",
            partial(self._set_log_level, carb.logging.LEVEL_INFO),
        ),
        ToolbarButton(
            "warning",
            "Warning",
            partial(self._set_log_level, carb.logging.LEVEL_WARN),
            text=" " + str(self._log_view.warnings_model.as_int),
        ),
        ToolbarButton(
            "error",
            "Error",
            partial(self._set_log_level, carb.logging.LEVEL_ERROR),
            text=" " + str(self._log_view.errors_model.as_int),
        ),
    ]
    ui.Spacer(width=3)
    self._search_field = SearchField(self._log_view.search)

    ui.Spacer()
    ToolbarButton("copy_logs", "Copy", lambda toolbar=self: _copy_console_logs(toolbar))
    ToolbarButton("clear", "Clear Console", self._log_view.clear)

    cmd_visible = self._ConsoleToolbar__cmd_input_visible_model.as_bool
    self._command_button.checked = cmd_visible
    self._command_button.tooltip = (
        "Disable Command Field" if cmd_visible else "Enable Command Field"
    )
    self._set_log_level(self._log_view.log_level)


def _build_ui(self, show_instance_id_button: bool = False) -> None:
    with ui.HStack(height=22, style_type_name_override="Toolbar.Frame"):
        _fill_toolbar(self, show_instance_id_button)
    self._v1d_layout = True


def _install_console_toolbar() -> None:
    if getattr(ConsoleToolbar._build_ui, "_v1d", False):
        return
    ConsoleToolbar._build_ui = _build_ui
    ConsoleToolbar._copy_console_logs = _copy_console_logs
    _build_ui._v1d = True


def _toolbar_row(window):
    frame = getattr(window, "frame", None)
    if frame is None:
        return None
    roots = ui.Inspector.get_children(frame)
    if not roots:
        return None
    for child in ui.Inspector.get_children(roots[0]):
        if isinstance(child, ui.HStack):
            return child
    return None


def _release_toolbar_widgets(toolbar) -> None:
    search = getattr(toolbar, "_search_field", None)
    if search is not None:
        search.destroy()
        toolbar._search_field = None
    filt = getattr(toolbar, "_filter_button", None)
    if filt is not None:
        filt.destroy()
        toolbar._filter_button = None


def _show_instance_id() -> bool:
    return bool(carb.settings.get_settings().get("/app/ovc_deployment"))


def _rebuild_existing_toolbar(window) -> bool:
    """Refill a console toolbar that was built before this patch. Leave the log view."""
    toolbar = getattr(window, "_toolbar", None)
    if toolbar is None:
        return False
    if getattr(toolbar, "_v1d_layout", False):
        return True
    row = _toolbar_row(window)
    if row is None:
        return False
    try:
        _release_toolbar_widgets(toolbar)
        row.clear()
        with row:
            _fill_toolbar(toolbar, _show_instance_id())
        toolbar._v1d_layout = True
    except Exception as exc:  # noqa: BLE001
        carb.log_warn(f"[v1d.pv] console toolbar rearrange failed: {exc}")
        return False
    return True


def _console_style() -> dict:
    style = copy.deepcopy(CONSOLE_WINDOW_STYLE)
    style["Toolbar.Button.Image::copy_logs"] = {
        "image_url": "${glyphs}/copy.svg",
        "color": 0xFFCCCCCC,
    }
    return style


async def apply_copy_console_logs_icon(attempts: int = 120) -> None:
    """Rearrange the Console toolbar and point Copy at the kit copy glyph."""
    _install_console_toolbar()
    style = _console_style()
    for _ in range(attempts):
        console = ui.Workspace.get_window(_CONSOLE_TITLE)
        if console is not None:
            try:
                # set_style replaces the frame stylesheet; must include the full console style.
                console.frame.set_style(style)
            except Exception as exc:  # noqa: BLE001
                carb.log_warn(f"[v1d.pv] console copy icon style failed: {exc}")
            if _rebuild_existing_toolbar(console):
                return
        await omni.kit.app.get_app().next_update_async()
    carb.log_warn("[v1d.pv] console toolbar was not rearranged")
