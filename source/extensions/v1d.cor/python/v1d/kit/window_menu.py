# SPDX-License-Identifier: MIT
"""v1d → Window menu toggles (Console-style checkmarks)."""

from __future__ import annotations

from typing import Callable

import omni.ui as ui
from omni.kit.menu.utils import MenuHelperExtension

from v1d.kit.square_menu import ensure_square_ticks

MENU_GROUP = "Window"


def wire_window_menu(
    helper: MenuHelperExtension,
    title: str,
    window: ui.Window,
    show_fn: Callable[[bool], None],
) -> None:
    ensure_square_ticks(MENU_GROUP)
    ui.Workspace.set_show_window_fn(title, show_fn)
    helper.menu_startup(title, title, MENU_GROUP)
    window.set_visibility_changed_fn(lambda _visible: helper.menu_refresh())


def unwire_window_menu(helper: MenuHelperExtension, title: str) -> None:
    helper.menu_shutdown()
    ui.Workspace.set_show_window_fn(title, None)
