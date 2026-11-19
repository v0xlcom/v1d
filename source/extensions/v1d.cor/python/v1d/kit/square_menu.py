# SPDX-License-Identifier: MIT
"""Default check/radio marks: 6 px squares for every Kit menu."""

from __future__ import annotations

import omni.kit.menu.utils as menu_utils
import omni.ui as ui
from omni.kit.menu.core import uiMenu, uiMenuItem
from omni.kit.menu.utils.app_menu import IconMenuDelegate

_SEEDED: set[str] = set()
_DEFAULT_INSTALLED = False


class SquareMenuDelegate(IconMenuDelegate):
    """Check and radio marks as small squares.

    Selected is the timeline cyan. Idle matches the console log background.
    Hover is the playhead magenta, including when the item is already selected.
    """

    _SQUARE = 6
    # ABGR.
    _CYAN = 0xFFE6BF26  # timeline lens, rgb(0.15, 0.75, 0.9)
    _LOG_BG = 0xFF24211F  # console LogView #1F2124
    _MAGENTA = 0xFFFF00FF  # playhead, rgb(1, 0, 1)

    def _tick_color(self, checked: bool, hovered: bool) -> int:
        if hovered:
            return self._MAGENTA
        if checked:
            return self._CYAN
        return self._LOG_BG

    def _place_square(self, item):
        if not getattr(item, "checkable", False):
            super()._build_item_tick(item)
            return None
        side = self._SQUARE
        pad = max(0.0, (self.TICK_SIZE - side) / 2.0)
        rect = None
        ui.Spacer(width=self.TICK_SPACING[0])
        with ui.VStack(width=self.TICK_SIZE):
            ui.Spacer()
            with ui.HStack(height=side):
                ui.Spacer(width=pad)
                rect = ui.Rectangle(
                    width=side,
                    height=side,
                    style={"background_color": self._tick_color(bool(item.checked), False)},
                )
                ui.Spacer()
            ui.Spacer()
        ui.Spacer(width=self.TICK_SPACING[1])
        return rect

    def _build_item_tick(self, item):
        self._place_square(item)

    def build_item(self, item):
        if isinstance(item, ui.Separator) or not isinstance(item, (uiMenu, uiMenuItem)):
            return super().build_item(item)

        square = None
        with ui.VStack():
            row = ui.HStack(height=0, style=self._build_item_get_style(item))
            with row:
                self._build_item_header(item)
                square = self._place_square(item)
                self._build_item_glyph(item)
                self._build_item_label(item)
                self._build_item_hotkey(item)
                self._build_item_subdir(item)
        if square is not None and hasattr(row, "set_mouse_hovered_fn"):

            def on_hover(hovered, rect=square, menu_item=item):
                rect.style = {
                    "background_color": self._tick_color(bool(menu_item.checked), bool(hovered))
                }

            row.set_mouse_hovered_fn(on_hover)
        return None


def install_default_square_ticks() -> None:
    """Use square ticks for every menu that does not set its own delegate."""
    global _DEFAULT_INSTALLED
    if _DEFAULT_INSTALLED:
        return
    inst = menu_utils.get_instance()
    creator = getattr(inst, "_menu_creator", None) if inst else None
    if creator is None:
        return
    if not isinstance(getattr(creator, "_icon_delegate", None), SquareMenuDelegate):
        creator._icon_delegate = SquareMenuDelegate()
        creator.rebuild_menus()
    _DEFAULT_INSTALLED = True


def ensure_square_ticks(menu_name: str) -> None:
    """Pin square ticks on one top-level menu. First call wins."""
    install_default_square_ticks()
    if menu_name in _SEEDED:
        return
    _SEEDED.add(menu_name)
    menu_utils.add_menu_items(
        [menu_utils.MenuItemDescription(name="v1d.square", show_fn=lambda: False)],
        menu_name,
        delegate=SquareMenuDelegate(),
    )
