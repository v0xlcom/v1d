# SPDX-License-Identifier: MIT
"""Preview + Timeline + Console dock layout; defaults in extension data/, overrides in user state."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import carb
import omni.kit.app
import omni.kit.async_engine
import omni.ui as ui

from v1d.pv.ui.console_toolbar import apply_copy_console_logs_icon

PREVIEW_WINDOW_TITLE = "Preview"
TIMELINE_WINDOW_TITLE = "Timeline"
CONSOLE_WINDOW_TITLE = "Console"
BUNDLED_WORKSPACE_NAME = "ui_workspace_default.json"

_DOCK_POS = {
    "BOTTOM": ui.DockPosition.BOTTOM,
    "TOP": ui.DockPosition.TOP,
    "LEFT": ui.DockPosition.LEFT,
    "RIGHT": ui.DockPosition.RIGHT,
    "SAME": ui.DockPosition.SAME,
}


def _settings():
    return carb.settings.get_settings()


def _state_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return Path(base) / "v1d" / "ui_workspace.json"


def _ext_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if not (parent / "data").is_dir():
            continue
        if (parent / "config" / "extension.toml").is_file():
            return parent
        if parent.name == "v1d.pv" and (parent / "data").is_dir():
            return parent
    return None


def _bundled_default_path() -> Path | None:
    root = _ext_root()
    if not root:
        return None
    return root / "data" / BUNDLED_WORKSPACE_NAME


def _write_json(path: Path, dump: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dump, indent=2) + "\n")


def save_as_default() -> bool:
    """Write the current dock layout as the layout restored on the next launch."""
    try:
        dump = ui.Workspace.dump_workspace()
    except Exception as exc:  # noqa: BLE001
        carb.log_warn(f"[v1d.pv] save default layout failed: {exc}")
        return False
    _write_json(_state_path(), dump)
    carb.log_info(f"[v1d.pv] saved default layout to {_state_path()}")
    return True


def save_workspace() -> None:
    if not _settings().get("/exts/v1d.pv/ui/workspace_persist"):
        return
    try:
        dump = ui.Workspace.dump_workspace()
    except Exception as exc:  # noqa: BLE001
        carb.log_warn(f"[v1d.pv] workspace dump failed: {exc}")
        return
    if not _settings().get_as_bool("/exts/v1d.pv/ui/console_hidden_by_default"):
        _set_console_visible_flag(dump, True)
    _write_json(_state_path(), dump)
    carb.log_info(f"[v1d.pv] saved UI workspace to {_state_path()}")


def _restore_dump(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        dump: list[Any] = json.loads(path.read_text())
        ui.Workspace.restore_workspace(dump, True)
        return True
    except Exception as exc:  # noqa: BLE001
        carb.log_warn(f"[v1d.pv] workspace restore failed ({path}): {exc}")
        return False


def save_bundled_default() -> bool:
    """Write extension data default (dev: set capture_workspace_default or call from tool)."""
    path = _bundled_default_path()
    if not path:
        carb.log_warn("[v1d.pv] cannot locate extension data/ for bundled workspace")
        return False
    try:
        dump = ui.Workspace.dump_workspace()
    except Exception as exc:  # noqa: BLE001
        carb.log_warn(f"[v1d.pv] bundled workspace dump failed: {exc}")
        return False
    _write_json(path, dump)
    carb.log_warn(f"[v1d.pv] wrote bundled UI default to {path}")
    return True


def _layout_anchor_title() -> str:
    return str(
        _settings().get("/exts/v1d.pv/ui/console_anchor")
        or _settings().get("/exts/v1d.pv/ui/timeline_anchor")
        or PREVIEW_WINDOW_TITLE
    )


def _dock_ratio(setting_key: str, default: float) -> float:
    return float(_settings().get(setting_key) or default)


def _dock_position(setting_key: str, default: str) -> ui.DockPosition:
    pos_name = str(_settings().get(setting_key) or default).upper()
    return _DOCK_POS.get(pos_name, ui.DockPosition.BOTTOM)


async def _ensure_workspace_dock(attempts: int = 90) -> None:
    """Preview in DockSpace; Timeline + Console docked to preview (split shell)."""
    settings = _settings()
    anchor_title = _layout_anchor_title()
    console_ratio = _dock_ratio("/exts/v1d.pv/ui/console_dock_ratio", 0.32)
    console_pos = _dock_position("/exts/v1d.pv/ui/console_dock_position", "RIGHT")
    tl_ratio = _dock_ratio("/exts/v1d.pv/ui/timeline_dock_ratio", 0.22)
    tl_pos = _dock_position("/exts/v1d.pv/ui/timeline_dock_position", "BOTTOM")

    for _ in range(attempts):
        dockspace = ui.Workspace.get_window("DockSpace")
        console = ui.Workspace.get_window(CONSOLE_WINDOW_TITLE)
        anchor = ui.Workspace.get_window(anchor_title)
        timeline = ui.Workspace.get_window(TIMELINE_WINDOW_TITLE)
        if not (anchor and timeline and console):
            await omni.kit.app.get_app().next_update_async()
            continue
        try:
            if dockspace:
                anchor.dock_in(dockspace, ui.DockPosition.SAME)
            timeline.dock_in(anchor, tl_pos, tl_ratio)
            timeline.visible = True
            console.dock_in(anchor, console_pos, console_ratio)
            console.visible = not settings.get_as_bool(
                "/exts/v1d.pv/ui/console_hidden_by_default"
            )
            return
        except Exception as exc:  # noqa: BLE001
            carb.log_warn(f"[v1d.pv] workspace dock failed: {exc}")
        await omni.kit.app.get_app().next_update_async()


def _set_console_visible_flag(node: Any, visible: bool) -> None:
    if isinstance(node, dict):
        if node.get("title") == CONSOLE_WINDOW_TITLE:
            node["visible"] = visible
        for child in node.get("children") or []:
            _set_console_visible_flag(child, visible)
    elif isinstance(node, list):
        for item in node:
            _set_console_visible_flag(item, visible)


async def _hide_console_after_restore(attempts: int = 45) -> None:
    """Console extension may show_window on startup after restore; re-hide when that is the default."""
    for _ in range(attempts):
        console = ui.Workspace.get_window(CONSOLE_WINDOW_TITLE)
        if console:
            console.visible = False
            return
        await omni.kit.app.get_app().next_update_async()


async def _show_console_after_restore(attempts: int = 45) -> None:
    """Quit can dump Console as hidden. Show it again when the default is visible."""
    for _ in range(attempts):
        console = ui.Workspace.get_window(CONSOLE_WINDOW_TITLE)
        if console:
            console.visible = True
            return
        await omni.kit.app.get_app().next_update_async()


async def apply_layout_when_ready() -> None:
    settings = _settings()
    restored = False

    if settings.get("/exts/v1d.pv/ui/workspace_persist") and _restore_dump(_state_path()):
        restored = True
    elif settings.get_as_bool("/exts/v1d.pv/ui/use_bundled_workspace_default"):
        bundled = _bundled_default_path()
        if bundled and _restore_dump(bundled):
            restored = True

    if not restored:
        await _ensure_workspace_dock()
    else:
        # Restored JSON defines Preview/Timeline/Console; do not re-dock (that broke user layout).
        await omni.kit.app.get_app().next_update_async()
        if settings.get_as_bool("/exts/v1d.pv/ui/console_hidden_by_default"):
            await _hide_console_after_restore()
        else:
            await _show_console_after_restore()

    await apply_copy_console_logs_icon()

    if settings.get("/exts/v1d.pv/ui/capture_workspace_default"):
        saved = save_bundled_default()
        if settings.get("/exts/v1d.pv/ui/capture_workspace_then_quit"):
            omni.kit.app.get_app().post_quit(0 if saved else 1)


_layout_sub = None
_layout_started = False


def _kick_layout_on_update(_event) -> None:
    global _layout_sub, _layout_started
    if _layout_started:
        return
    _layout_started = True
    if _layout_sub is not None:
        _layout_sub.unsubscribe()
        _layout_sub = None
    omni.kit.async_engine.run_coroutine(apply_layout_when_ready())


def schedule_layout() -> None:
    """Call from extension startup; layout runs on first app update (async engine ready)."""
    global _layout_sub, _layout_started
    if _settings().get("/exts/v1d.pv/s2_bench"):
        return
    _layout_started = False
    stream = omni.kit.app.get_app().get_update_event_stream()
    _layout_sub = stream.create_subscription_to_pop(_kick_layout_on_update, name="v1d.pv.ui.layout")
