# SPDX-License-Identifier: MIT
"""Wipe compare: original (left) vs upscaled (right)."""

from __future__ import annotations

import omni.ui as ui

_FRAME_STYLE = {"background_color": 0x00000000}


def downscale_rgba_nn(rgba: bytes, sw: int, sh: int, dw: int, dh: int) -> bytes:
    if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0:
        return b""
    if sw == dw and sh == dh:
        return rgba
    out = bytearray(dw * dh * 4)
    for y in range(dh):
        sy = min(sh - 1, y * sh // dh)
        for x in range(dw):
            sx = min(sw - 1, x * sw // dw)
            si = (sy * sw + sx) * 4
            oi = (y * dw + x) * 4
            out[oi : oi + 4] = rgba[si : si + 4]
    return bytes(out)


class WipeCompare:
    def __init__(self, height: int = 400) -> None:
        self._split = 0.5
        self._view_w = 640
        self._view_h = height
        self._dragging = False
        self._orig = ui.ByteImageProvider()
        self._up = ui.ByteImageProvider()
        self._clip_frame: ui.Frame | None = None
        self._handle_placer: ui.Placer | None = None
        self._outer: ui.Frame | None = None
        self._stack: ui.ZStack | None = None
        self._orig_iwp: ui.ImageWithProvider | None = None

        with ui.Frame(
            width=ui.Fraction(1),
            height=ui.Pixel(height),
            horizontal_clipping=True,
        ) as outer:
            self._outer = outer
            outer.set_computed_content_size_changed_fn(self._on_outer_size)
            with ui.ZStack(
                width=ui.Fraction(1),
                height=ui.Fraction(1),
                mouse_pressed_fn=self._on_mouse_pressed,
                mouse_moved_fn=self._on_mouse_moved,
                mouse_released_fn=self._on_mouse_released,
            ) as stack:
                self._stack = stack
                ui.ImageWithProvider(
                    self._up,
                    width=ui.Fraction(1),
                    height=ui.Fraction(1),
                    fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                )
                with ui.Placer(offset_x=0, stable_size=True):
                    with ui.Frame(
                        width=ui.Pixel(1),
                        height=ui.Fraction(1),
                        horizontal_clipping=True,
                        style=_FRAME_STYLE,
                    ) as frame:
                        self._clip_frame = frame
                        self._orig_iwp = ui.ImageWithProvider(
                            self._orig,
                            width=ui.Pixel(self._view_w),
                            height=ui.Fraction(1),
                            fill_policy=ui.IwpFillPolicy.IWP_STRETCH,
                            alignment=ui.Alignment.LEFT,
                        )
                with ui.Placer(offset_x=0, stable_size=True) as handle_placer:
                    self._handle_placer = handle_placer
                    ui.Rectangle(
                        width=4,
                        height=ui.Fraction(1),
                        style={"background_color": 0xFFCCCCCC},
                    )

        self._apply_split()

    def _on_outer_size(self) -> None:
        if self._outer is None:
            return
        w = int(self._outer.computed_content_width)
        h = int(self._outer.computed_content_height)
        if w > 1:
            self._view_w = w
        if h > 1:
            self._view_h = h
        self._apply_split()

    def _split_px(self) -> int:
        return max(0, min(self._view_w, int(self._view_w * self._split)))

    def _apply_split(self) -> None:
        px = self._split_px()
        if self._orig_iwp is not None:
            self._orig_iwp.width = ui.Pixel(self._view_w)
        if self._clip_frame is not None:
            self._clip_frame.width = ui.Pixel(px)
        if self._handle_placer is not None:
            self._handle_placer.offset_x = ui.Pixel(px)

    def _set_split_from_x(self, x: float) -> None:
        if self._view_w <= 0:
            return
        px = max(0, min(self._view_w, int(x)))
        self._split = px / float(self._view_w)
        self._apply_split()

    def _on_mouse_pressed(self, x: float, y: float, button: int, _: int) -> None:
        if button != 0:
            return
        self._dragging = True
        self._set_split_from_x(x)

    def _on_mouse_moved(self, x: float, y: float, button: int, _: int) -> None:
        if not self._dragging:
            return
        self._set_split_from_x(x)

    def _on_mouse_released(self, x: float, y: float, button: int, _: int) -> None:
        if button == 0:
            self._dragging = False

    def set_original_gpu(self, ptr: int, width: int, height: int) -> None:
        self._orig.set_bytes_data_from_gpu(int(ptr), [width, height])

    def set_upscaled_gpu(self, ptr: int, width: int, height: int, stride: int = 0) -> None:
        if stride <= 0:
            stride = width * 4
        self._up.set_bytes_data_from_gpu(int(ptr), [width, height], stride=stride)
        self._apply_split()

    def clear(self) -> None:
        self._orig.set_bytes_data([], [0, 0])
        self._up.set_bytes_data([], [0, 0])
