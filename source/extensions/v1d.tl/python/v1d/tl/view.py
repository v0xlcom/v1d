# SPDX-License-Identifier: MIT
"""Timeline ruler view math (no Kit imports)."""

from __future__ import annotations

import math

_TICK_STEPS = (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800)
MIN_CELL_PX = 2
_MAX_PX_PER_FRAME = 1e6


class TimelineView:
    def __init__(self, frame_count: int = 0, width_px: float = 0.0) -> None:
        self.frame_count = max(0, int(frame_count))
        self.width_px = max(0.0, float(width_px))
        self.px_per_frame = 1.0
        self.origin = 0.0
        self.fps = 30.0
        self.align_on_play = False
        if self.frame_count > 0 and self.width_px >= 1.0:
            self.fit()

    @property
    def frame_max(self) -> int:
        return max(0, self.frame_count - 1)

    def px_min(self) -> float:
        if self.width_px < 1.0:
            return 1.0
        return self.width_px / max(self.frame_count, 1)

    def px_max(self) -> float:
        """Closest zoom: exactly one second (``fps`` frames) across the window."""
        if self.width_px < 1.0:
            return 1.0
        one_second = self.width_px / max(self.fps, 1.0)
        return max(self.px_min(), one_second)

    def _sanitize_zoom_state(self) -> None:
        if self.frame_count <= 0 or self.width_px < 1.0:
            return
        lo = self.px_min()
        hi = min(self.px_max(), _MAX_PX_PER_FRAME)
        px = self.px_per_frame
        if not math.isfinite(px) or px <= 0.0:
            px = lo
        self.px_per_frame = min(hi, max(lo, px))
        origin = self.origin
        if not math.isfinite(origin):
            origin = 0.0
        pan = self.pan_max()
        self.origin = max(0.0, min(pan, float(origin)))

    def set_fps(self, fps: float) -> None:
        self.fps = max(1.0, float(fps))
        if self.frame_count > 0 and self.width_px >= 1.0:
            self._sanitize_zoom_state()
            self.set_origin(self.origin)

    def grid_visible(self) -> bool:
        """One frame is at least 1 px white plus 1 px dark."""
        return self.px_per_frame + 1e-6 >= float(MIN_CELL_PX)

    def pan_max(self) -> float:
        if self.frame_count <= 0 or self.px_per_frame <= 0.0:
            return 0.0
        return max(0.0, self.frame_count - self.width_px / self.px_per_frame)

    def set_width_px(self, width: float) -> None:
        new_w = max(0.0, float(width))
        span = None
        if self.width_px >= 1.0 and self.px_per_frame > 0.0 and self.frame_count > 0:
            span = self.width_px / self.px_per_frame
        self.width_px = new_w
        if self.frame_count <= 0 or self.width_px < 1.0:
            return
        if span is None:
            self.fit()
            return
        self.px_per_frame = self.width_px / max(span, 1e-6)
        self._sanitize_zoom_state()

    def set_frame_count(self, frame_count: int) -> None:
        self.frame_count = max(0, int(frame_count))
        if self.frame_count > 0 and self.width_px >= 1.0:
            self.fit()
        else:
            self.origin = 0.0
            self.px_per_frame = 1.0

    def fit(self) -> None:
        self.origin = 0.0
        if self.frame_count > 0 and self.width_px >= 1.0:
            self.px_per_frame = self.px_min()
            self._sanitize_zoom_state()

    def set_origin(self, origin: float) -> None:
        self.origin = max(0.0, min(self.pan_max(), float(origin)))

    def frame_at_x(self, x: float) -> int:
        fm = self.frame_max
        if self.frame_count <= 0:
            return 0
        px = self.px_per_frame
        if not math.isfinite(px) or px <= 0.0:
            return max(0, min(fm, int(round(self.origin))))
        raw = round(self.origin + float(x) / px)
        return max(0, min(fm, raw))

    def x_at_frame(self, frame: int) -> float:
        px = self.px_per_frame
        if not math.isfinite(px):
            px = self.px_min()
        x = (int(frame) - self.origin) * px
        if not math.isfinite(x):
            return 0.0
        return x

    def anchor_frame(self, playhead: int) -> int:
        x = self.x_at_frame(playhead)
        if 0.0 <= x <= self.width_px:
            return int(playhead)
        return self.frame_at_x(self.width_px * 0.5)

    def zoom(self, factor: float, anchor_frame: int) -> None:
        if self.frame_count <= 0 or self.width_px < 1.0:
            return
        old_px = self.px_per_frame
        anchor_x = self.x_at_frame(anchor_frame)
        lo = self.px_min()
        hi = self.px_max()
        new_px = old_px * factor
        if new_px < lo:
            new_px = lo
        elif new_px > hi:
            new_px = hi
        if abs(new_px - old_px) < 1e-9:
            return
        self.px_per_frame = new_px
        self.origin = float(anchor_frame) - anchor_x / new_px
        self._sanitize_zoom_state()

    def tick_step(self) -> int:
        if self.px_per_frame <= 0.0:
            return 1
        for step in _TICK_STEPS:
            if step * self.px_per_frame >= 64.0:
                return step
        return _TICK_STEPS[-1]

    def visible_ticks(self) -> list[int]:
        if self.frame_count <= 0 or self.width_px < 1.0:
            return []
        step = self.tick_step()
        fm = self.frame_max
        ticks: list[int] = []
        f = 0
        while f <= fm:
            x = self.x_at_frame(f)
            if 0.0 <= x <= self.width_px:
                ticks.append(f)
            f += step
        for end in (0, fm):
            x = self.x_at_frame(end)
            if 0.0 <= x <= self.width_px and end not in ticks:
                ticks.append(end)
        ticks.sort()
        return ticks

    def follow(self, frame: int, direction: int) -> None:
        if self.width_px < 1.0:
            return
        if self.align_on_play:
            self.align_on_play = False
            if direction >= 0:
                self.origin = float(frame)
            else:
                self.origin = float(frame) - self.width_px / self.px_per_frame
            self.set_origin(self.origin)
            return
        x = self.x_at_frame(frame)
        if 0.0 <= x <= self.width_px:
            return
        if x > self.width_px:
            # Forward: bar jumps ahead, playhead on its left edge.
            # Reverse: playhead was beyond the right, bring it back inside.
            target_x = 0.0 if direction >= 0 else 0.8 * self.width_px
        else:
            # Reverse: bar jumps back, playhead on its right edge.
            target_x = 0.2 * self.width_px if direction >= 0 else self.width_px
        self.origin = float(frame) - target_x / self.px_per_frame
        self.set_origin(self.origin)

    def visible_span_frames(self) -> float:
        if self.frame_count <= 0 or self.px_per_frame <= 0.0:
            return float(max(self.frame_count, 1))
        return self.width_px / self.px_per_frame

    def zoom_percent(self) -> float:
        """Visible sequence fraction: 100 = full sequence in the window."""
        total = max(self.frame_count, 1)
        span = min(self.visible_span_frames(), float(total))
        return 100.0 * span / float(total)

    def min_zoom_percent(self) -> float:
        if self.frame_count <= 0 or self.width_px < 1.0:
            return 100.0
        total = float(max(self.frame_count, 1))
        hi_px = max(self.px_max(), 1e-9)
        min_span = self.width_px / hi_px
        return min(100.0, 100.0 * min_span / total)

    def set_zoom_percent(self, percent: float, anchor_frame: int, *, center: bool = False) -> None:
        if self.frame_count <= 0 or self.width_px < 1.0:
            return
        lo_pct = self.min_zoom_percent()
        hi_pct = 100.0
        pct = max(lo_pct, min(hi_pct, float(percent)))
        total = float(max(self.frame_count, 1))
        span = total * (pct / 100.0)
        hi_px = self.px_max()
        lo_px = self.px_min()
        min_span = self.width_px / hi_px
        max_span = total
        span = max(min_span, min(max_span, span))
        new_px = self.width_px / max(span, 1e-6)
        new_px = min(hi_px, max(lo_px, new_px))
        self.px_per_frame = new_px
        if center:
            self.origin = float(anchor_frame) - (self.width_px * 0.5) / new_px
        else:
            anchor_x = self.x_at_frame(anchor_frame)
            self.origin = float(anchor_frame) - anchor_x / new_px
        self._sanitize_zoom_state()

    def center_frame(self, frame: int) -> None:
        if self.frame_count <= 0 or self.width_px < 1.0 or self.px_per_frame <= 0.0:
            return
        self.origin = float(frame) - (self.width_px * 0.5) / self.px_per_frame
        self._sanitize_zoom_state()

    def overview_frame_body_width(self, overview_width_px: float) -> float:
        ow = max(0.0, float(overview_width_px))
        fc = max(self.frame_count, 1)
        if fc <= 0:
            return ow
        if fc == 1:
            return ow
        return (ow - float(fc - 1)) / float(fc)

    def overview_pitch(self, overview_width_px: float) -> float:
        fw = self.overview_frame_body_width(overview_width_px)
        if self.frame_count <= 1:
            return fw
        return fw + 1.0

    def overview_frame_rect(self, frame: int, overview_width_px: float) -> tuple[float, float]:
        if self.frame_count <= 0:
            return 0.0, 0.0
        fw = self.overview_frame_body_width(overview_width_px)
        k = int(frame)
        if k < 0 or k >= self.frame_count:
            return 0.0, 0.0
        pitch = self.overview_pitch(overview_width_px)
        return float(k) * pitch, fw

    def overview_divider_x(self, after_frame: int, overview_width_px: float) -> float:
        left, fw = self.overview_frame_rect(after_frame, overview_width_px)
        return left + fw

    @staticmethod
    def split_frame_gap(x: float, w: float) -> tuple[int, int, int]:
        """1px light gap at the frame start, then the dark body until the next frame.

        Returns ``(gap_x, body_x, body_w)`` in whole pixels. ``body_w`` is 0 when the
        slot is too narrow for a gap plus a body.
        """
        gap = int(round(x))
        end = int(round(x + w))
        body_x = gap + 1
        body_w = end - body_x
        if body_w < 1:
            return gap, body_x, 0
        return gap, body_x, body_w

    def frames_per_cell(self) -> int:
        if self.px_per_frame <= 0.0:
            return 1
        if self.px_per_frame >= MIN_CELL_PX:
            return 1
        return max(1, int(math.ceil(MIN_CELL_PX / self.px_per_frame)))

    def detail_cells_grouped(self, max_cells: int) -> list[tuple[int, int, float, float]]:
        """Visible detail cells as (start_frame, n_frames, x, width). Respects ``max_cells``."""
        if self.frame_count <= 0 or self.width_px < 1.0 or self.px_per_frame <= 0.0:
            return []
        cap = max(1, int(max_cells))
        group = self.frames_per_cell()
        px = self.px_per_frame
        first = max(0, int(math.floor(self.origin)))
        last = min(self.frame_max, int(math.ceil(self.origin + self.width_px / px)) - 1)
        if last < first:
            last = first
        while True:
            cells: list[tuple[int, int, float, float]] = []
            frame = first
            while frame <= last:
                n = min(group, last - frame + 1)
                x = (frame - self.origin) * px
                w = n * px
                if x + w >= 0.0 and x <= self.width_px:
                    cells.append((frame, n, x, w))
                frame += n
            if len(cells) <= cap or group >= self.frame_count:
                return cells
            group *= 2

    def detail_grid(self, max_cells: int) -> list[tuple[int, int, int, int]]:
        """Even cells ``(start_frame, n_frames, x_px, pitch_px)``.

        One frame per cell. Every white gap is ``pitch_px`` apart. Empty when a
        frame would be thinner than 1 px white plus 1 px dark, or when more
        cells would be needed than ``max_cells``.
        """
        if self.frame_count <= 0 or self.width_px < 1.0 or self.px_per_frame <= 0.0:
            return []
        if not self.grid_visible():
            return []
        px = self.px_per_frame
        if not math.isfinite(px) or px <= 0.0:
            return []
        cap = max(1, int(max_cells))
        pitch = max(MIN_CELL_PX, int(round(min(px, float(self.width_px)))))
        first = max(0, int(math.floor(self.origin)))
        x = int(round((first - self.origin) * self.px_per_frame))
        cells: list[tuple[int, int, int, int]] = []
        frame = first
        while frame <= self.frame_max:
            if x >= self.width_px:
                break
            if x + pitch >= 0:
                cells.append((frame, 1, x, pitch))
            if len(cells) > cap:
                return []
            frame += 1
            x += pitch
        return cells

    def gap_x_for_frame(self, frame: int, cells: list[tuple[int, int, int, int]]) -> int | None:
        """Pixel of the white gap where ``frame`` starts (the frame shown in preview)."""
        if not cells:
            return None
        frame = int(frame)
        for start, n, x, _pitch in cells:
            if start <= frame < start + n:
                return x
        return None

    def layout_pitch_px(self) -> int:
        """Horizontal pitch of one sequence frame in the detail grid (matches ``detail_grid``)."""
        px = self.px_per_frame
        if not math.isfinite(px) or px <= 0.0:
            return MIN_CELL_PX
        if self.grid_visible():
            return max(MIN_CELL_PX, int(round(min(px, float(self.width_px)))))
        return max(1, int(round(px)))

    def frame_gap_x(self, frame: int) -> int:
        """X of the vertical grid line (white gap) where ``frame`` starts.

        Same stepping as ``detail_grid`` (integer pitch from the first visible frame).
        """
        frame = int(frame)
        if self.frame_count <= 0:
            return 0
        pitch = self.layout_pitch_px()
        first = max(0, int(math.floor(self.origin)))
        x_first = int(round((first - self.origin) * self.px_per_frame))
        if frame <= first:
            return int(round((frame - self.origin) * self.px_per_frame))
        return x_first + (frame - first) * pitch

    def frame_at_grid_x(self, x: float) -> int:
        """Sequence frame whose grid gap is at or just left of ``x``."""
        fm = self.frame_max
        if self.frame_count <= 0:
            return 0
        pitch = max(1, self.layout_pitch_px())
        first = max(0, int(math.floor(self.origin)))
        x_first = self.frame_gap_x(first)
        rel = int(math.floor((float(x) - float(x_first)) / float(pitch)))
        return max(0, min(fm, first + rel))

    def clip_rect_px(self, start_frame: int, end_inclusive: int) -> tuple[int, int]:
        """Clip span on the frame scale: left x and width through ``end_inclusive``.

        Same mapping as the Frames ruler (``x_at_frame``). A 600-frame clip
        (frames 0 through 599) stays 600 frames wide at every zoom.
        """
        x0 = int(round(self.x_at_frame(int(start_frame))))
        x1 = int(round(self.x_at_frame(int(end_inclusive) + 1)))
        return x0, max(0, x1 - x0)

    def detail_cells(self, max_cells: int) -> list[tuple[int, float, float]]:
        """Visible frames as (frame, x, width). One frame is one cell when the pool allows."""
        if self.frame_count <= 0 or self.width_px < 1.0 or self.px_per_frame <= 0.0:
            return []
        px = self.px_per_frame
        first = max(0, int(math.floor(self.origin)))
        last = min(self.frame_max, int(math.ceil(self.origin + self.width_px / px)) - 1)
        if last < first:
            last = first
        count = last - first + 1
        step = 1
        cap = max(1, int(max_cells))
        if count > cap:
            step = (count + cap - 1) // cap
        cells: list[tuple[int, float, float]] = []
        frame = first
        while frame <= last:
            span = min(step, last - frame + 1)
            x = (frame - self.origin) * px
            w = span * px
            if x + w >= 0.0 and x <= self.width_px:
                cells.append((frame, x, w))
            frame += step
        return cells

    def overview_cells(self, overview_width_px: float, max_cells: int) -> list[tuple[int, float, float]]:
        """Full clip tiled across the pan strip. One frame is one cell when the pool allows."""
        ow = max(0.0, float(overview_width_px))
        fc = self.frame_count
        if fc <= 0 or ow < 1.0:
            return []
        cap = max(1, int(max_cells))
        step = 1 if fc <= cap else (fc + cap - 1) // cap
        cells: list[tuple[int, float, float]] = []
        frame = 0
        while frame < fc:
            end = min(fc, frame + step)
            x0 = round(frame / fc * ow)
            x1 = round(end / fc * ow)
            if x1 > x0:
                cells.append((frame, float(x0), float(x1 - x0)))
            frame = end
        return cells

    def overview_viewport(self, overview_width_px: float) -> tuple[float, float]:
        """Visible ruler range as a fraction of the full clip on the pan strip."""
        ow = max(0.0, float(overview_width_px))
        if ow <= 0.0 or self.frame_count <= 0:
            return 0.0, 0.0
        fc = float(max(self.frame_count, 1))
        span = min(self.visible_span_frames(), fc)
        width_px = min(ow, (span / fc) * ow)
        left_px = (self.origin / fc) * ow
        left_px = max(0.0, min(left_px, ow - width_px))
        return left_px, width_px

    def overview_x_at_frame(self, frame: int, overview_width_px: float) -> float:
        ow = max(0.0, float(overview_width_px))
        return (int(frame) / max(self.frame_count, 1)) * ow

    def frame_at_overview_x(self, x: float, overview_width_px: float) -> int:
        ow = max(0.0, float(overview_width_px))
        if ow <= 0.0:
            return 0
        fc = max(self.frame_count, 1)
        raw = int(round(float(x) / ow * fc))
        return max(0, min(self.frame_max, raw))

    def origin_from_overview_left(self, left_px: float, overview_width_px: float) -> None:
        ow = max(0.0, float(overview_width_px))
        if ow <= 0.0:
            return
        fc = max(self.frame_count, 1)
        origin = float(left_px) / ow * fc
        self.set_origin(origin)

    def center_on_overview_x(self, x: float, overview_width_px: float) -> None:
        frame = self.frame_at_overview_x(x, overview_width_px)
        self.set_origin(float(frame) - self.visible_span_frames() / 2.0)

    def zoom_to_span(self, span_frames: float, anchor_frame: int, anchor_edge: str) -> None:
        if self.frame_count <= 0 or self.width_px < 1.0:
            return
        hi_px = self.px_max()
        min_span = self.width_px / hi_px
        max_span = float(self.frame_count)
        span = max(min_span, min(max_span, float(span_frames)))
        new_px = self.width_px / span
        lo_px = self.px_min()
        if new_px < lo_px:
            new_px = lo_px
            span = self.width_px / new_px
        elif new_px > hi_px:
            new_px = hi_px
            span = self.width_px / new_px
        if anchor_edge == "right":
            origin = float(anchor_frame) - span
        else:
            origin = self.origin
        self.px_per_frame = new_px
        self.origin = origin
        self.set_origin(self.origin)

    def right_edge_frame(self) -> float:
        return self.origin + self.visible_span_frames()


def clip_trim_edge_px(width: int, edge_px: int = 10) -> int:
    """Grab width on each end. A narrow clip keeps a body in the middle."""
    span = max(0, int(width))
    edge = max(1, int(edge_px))
    if span < 1:
        return edge
    if span < edge * 2 + 4:
        return max(1, span // 4)
    return edge


def clip_edge_zone(
    x: float,
    left: int,
    width: int,
    edge_px: int = 10,
    *,
    left_visible: bool = True,
    right_visible: bool = True,
) -> str:
    """Hit on a clip rectangle: ``trim_left``, ``trim_right``, ``body``, or ``outside``.

    End bars are the resize targets. A couple of pixels outside the rect still
    count, so the border can be grabbed. An edge scrolled off the strip is not
    a trim target.
    """
    span = max(0, int(width))
    if span < 1:
        return "outside"
    left_i = int(left)
    right = left_i + span
    edge = clip_trim_edge_px(span, edge_px)
    xf = float(x)
    on_left = bool(left_visible) and (left_i - 2) <= xf <= (left_i + edge)
    on_right = bool(right_visible) and (right - edge) <= xf <= (right + 2)
    if on_left and on_right:
        return "trim_left" if xf < (left_i + right) * 0.5 else "trim_right"
    if on_left:
        return "trim_left"
    if on_right:
        return "trim_right"
    if left_i <= xf < right:
        return "body"
    return "outside"


def wheel_zoom_direction(
    up: float,
    down: float,
    prev_up: float,
    prev_down: float,
) -> bool | None:
    """True = zoom in, False = zoom out, None = ignore this callback.

    ``mouse_wheel_fn`` fires once per notch and does not pass a delta.
    ``SCROLL_UP`` / ``SCROLL_DOWN`` are often the same level on every notch
    in that direction (1, 0), not a running total. A changed counter still
    wins, so a cumulative device keeps working.
    """
    dup = float(up) - float(prev_up)
    ddown = float(down) - float(prev_down)
    if dup > 1e-3 or ddown > 1e-3:
        if abs(dup - ddown) <= 1e-3:
            return None
        return dup > ddown
    if float(up) > float(down) + 1e-3:
        return True
    if float(down) > float(up) + 1e-3:
        return False
    return None


def next_wheel_zoom_percent(
    current_pct: float,
    zoom_in: bool,
    *,
    step_pct: float = 5.0,
    lo_pct: float,
    hi_pct: float = 100.0,
) -> float | None:
    """Next zoom on the wheel ladder from actual percent (not display rounding)."""
    step = max(float(step_pct), 1e-6)
    lo = float(lo_pct)
    hi = float(hi_pct)
    cur = float(current_pct)
    if zoom_in:
        if cur <= lo + 1e-6:
            return None
        raw = cur - step
        target = math.floor(raw / step + 1e-9) * step
        if target < lo:
            target = lo
        if target >= cur - 1e-6:
            return None
        return target
    if cur >= hi - 1e-6:
        return None
    raw = cur + step
    target = math.ceil(raw / step - 1e-9) * step
    if target > hi:
        target = hi
    if target <= cur + 1e-6:
        return None
    return target
