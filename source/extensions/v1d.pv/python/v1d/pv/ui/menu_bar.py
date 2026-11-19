# SPDX-License-Identifier: MIT
"""Main menu bar controls (top-level, right-aligned)."""

from __future__ import annotations

from typing import Callable

import omni.kit.menu.utils as menu_utils
import omni.ui as ui
from omni.kit.menu.utils import MenuAlignment


class _ReloadMenuDelegate(ui.MenuDelegate):
    def __init__(self, on_reload: Callable[[], None]) -> None:
        super().__init__()
        self._on_reload = on_reload

    def get_menu_alignment(self):
        return MenuAlignment.RIGHT

    def build_item(self, item: ui.MenuHelper):
        with ui.HStack(width=0):
            with ui.VStack(content_clipping=1, width=0):
                ui.Button("Reload", width=72, clicked_fn=self._on_reload)


_reload_menu: list | None = None
_reload_delegate: _ReloadMenuDelegate | None = None


def install_reload_button(on_reload: Callable[[], None]) -> None:
    global _reload_menu, _reload_delegate
    if _reload_menu is not None:
        return
    _reload_delegate = _ReloadMenuDelegate(on_reload)
    _reload_menu = menu_utils.add_menu_items([], "Reload", 100, delegate=_reload_delegate)
    inst = menu_utils.get_instance()
    creator = getattr(inst, "_menu_creator", None) if inst else None
    if creator is not None and hasattr(creator, "set_right_padding"):
        creator.set_right_padding(8)


def remove_reload_button() -> None:
    global _reload_menu, _reload_delegate
    if _reload_menu is None:
        return
    menu_utils.remove_menu_items(_reload_menu, "Reload")
    _reload_menu = None
    _reload_delegate = None


_file_menu: list | None = None


def _open_video() -> None:
    import subprocess

    import carb
    from v1d.ngn.session import ScrubSession

    try:
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                "--title=Open video",
                "--file-filter=Video | *.mp4 *.mov *.mkv *.m4v *.webm",
                "--file-filter=All files | *",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        carb.log_error("[v1d.pv] zenity is not installed; File → Open Video needs it")
        return
    if result.returncode != 0:
        return
    path = result.stdout.strip()
    if not path:
        return
    try:
        ScrubSession.get().open_clip(path)
    except Exception as exc:  # noqa: BLE001
        carb.log_error(f"[v1d.pv] open video: {exc}")


def _quit_app() -> None:
    import carb
    import omni.kit.app

    try:
        from v1d.pv.ui import workspace_layout

        workspace_layout.save_workspace()
    except Exception as exc:  # noqa: BLE001
        carb.log_warn(f"[v1d.pv] Quit: workspace save skipped: {exc}")
    # Keep fastShutdown false so extension shutdown still releases the engine.
    omni.kit.app.get_app().post_quit(0)


def _hook(name: str) -> None:
    from v1d.kit import project_hooks

    project_hooks.call(name)


def install_file_menu() -> None:
    global _file_menu
    if _file_menu is not None:
        return
    from v1d.kit.square_menu import ensure_square_ticks

    ensure_square_ticks("File")
    items = [
        menu_utils.MenuItemDescription(name="New .v1d", onclick_fn=lambda: _hook("new")),
        menu_utils.MenuItemDescription(name="Open .v1d", onclick_fn=lambda: _hook("open")),
        menu_utils.MenuItemDescription(name="Save .v1d", onclick_fn=lambda: _hook("save")),
        menu_utils.MenuItemDescription(name="Add Video", onclick_fn=lambda: _hook("add_video")),
        menu_utils.MenuItemDescription(name="Open Video", onclick_fn=_open_video),
        menu_utils.MenuItemDescription(name="Render", onclick_fn=lambda: _hook("show_render")),
        menu_utils.MenuItemDescription(name="Quit", header="", onclick_fn=_quit_app),
    ]
    _file_menu = menu_utils.add_menu_items(items, "File", -100)


def remove_file_menu() -> None:
    global _file_menu
    if _file_menu is None:
        return
    menu_utils.remove_menu_items(_file_menu, "File")
    _file_menu = None


_power_menu: list | None = None


def _select_power(profile_id: str) -> None:
    import carb

    from v1d.pv.ui.power_profile import set_profile

    ok, err = set_profile(profile_id)
    if not ok:
        carb.log_error(f"[v1d.pv] Power: {err}")
        return
    menu_utils.refresh_menu_items("Power")


def install_power_menu() -> None:
    """Top-bar Power menu: Performance, Balanced, Powersave."""
    global _power_menu
    if _power_menu is not None:
        return
    from v1d.kit.square_menu import ensure_square_ticks
    from v1d.pv.ui.power_profile import PROFILES, active_profile

    ensure_square_ticks("Power")
    items = []
    for label, profile_id in PROFILES:
        items.append(
            menu_utils.MenuItemDescription(
                name=label,
                ticked=True,
                ticked_fn=lambda pid=profile_id: active_profile() == pid,
                radio_group="v1d.power",
                onclick_fn=lambda pid=profile_id: _select_power(pid),
            )
        )
    _power_menu = menu_utils.add_menu_items(items, "Power", -50)


_layout_menu: list | None = None


def _save_layout_default() -> None:
    import carb

    from v1d.pv.ui import workspace_layout

    if not workspace_layout.save_as_default():
        carb.log_error("[v1d.pv] Layout: could not save the current layout")


def install_layout_menu() -> None:
    global _layout_menu
    if _layout_menu is not None:
        return
    items = [
        menu_utils.MenuItemDescription(name="Save as default", onclick_fn=_save_layout_default),
    ]
    _layout_menu = menu_utils.add_menu_items(items, "Layout", -75)


def remove_layout_menu() -> None:
    global _layout_menu
    if _layout_menu is None:
        return
    menu_utils.remove_menu_items(_layout_menu, "Layout")
    _layout_menu = None


def remove_power_menu() -> None:
    global _power_menu
    if _power_menu is None:
        return
    menu_utils.remove_menu_items(_power_menu, "Power")
    _power_menu = None
