# SPDX-License-Identifier: MIT
"""Lens timeline strip (omni.ui_scene, fixed shape pool)."""

from __future__ import annotations

import math

import omni.ui as ui
from omni.ui import color as cl
from omni.ui_scene import scene as sc

from v1d.tl.view import TimelineView

FULL_H = 28
LENS_H = 28
DETAIL_H = 64
TOTAL_H = FULL_H + LENS_H + DETAIL_H
CELL_POOL = 128

# Column-major ortho: x,y in [-1, 1], z in [-2, 2], camera at origin looking down -Z.
_ORTHO_PROJ = [
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, -0.5, 0.0,
    0.0, 0.0, 0.0, 1.0,
]
_ORTHO_VIEW = [
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
]

_CLR_TRACK = cl(0.78, 0.78, 0.78, 1.0)
_CLR_VIEWPORT = cl(0.23, 0.48, 0.60, 0.55)
_CLR_DETAIL_BG = cl(0.93, 0.93, 0.93, 1.0)
_CLR_FRAME = cl(0.10, 0.10, 0.10, 1.0)
_CLR_EDGE = cl(1.0, 1.0, 1.0, 1.0)
_CLR_PLAYHEAD = cl(1.0, 0.25, 1.0, 1.0)
_LENS_MESH_RGBA = [0.23, 0.48, 0.60, 0.35]


def _scene_point(x_px: float, y_px: float, w_px: float) -> list[float]:
    sx = 2.0 / max(w_px, 1.0)
    sy = 2.0 / float(TOTAL_H)
    return [-1.0 + x_px * sx, 1.0 - y_px * sy, 0.0]


def _xf_rect(x: float, y: float, pw: float, ph: float, w_px: float) -> sc.Matrix44:
    sx = 2.0 / max(w_px, 1.0)
    sy = 2.0 / float(TOTAL_H)
    scale_w = max(pw * sx, 1e-6)
    scale_h = max(ph * sy, 1e-6)
    cx = -1.0 + x * sx + scale_w * 0.5
    cy = 1.0 - y * sy - scale_h * 0.5
    return sc.Matrix44.get_translation_matrix(cx, cy, 0.0) * sc.Matrix44.get_scale_matrix(scale_w, scale_h, 1.0)


class LensTimelineStrip:
    """Single SceneView: Full + Lens + Detail bands."""

    def __init__(self) -> None:
        self._width_px = 0.0
        # Ortho frustum is the widget in NDC [-1, 1]. Construct this SceneView
        # inside an omni.ui `with` block so it is parented into the window.
        self._scene_view = sc.SceneView(
            sc.CameraModel(_ORTHO_PROJ, _ORTHO_VIEW),
            aspect_ratio_policy=sc.AspectRatioPolicy.STRETCH,
            width=ui.Fraction(1),
            height=ui.Fraction(1),
        )
        self._band_xfs: list[sc.Transform] = []
        self._viewport_xf: sc.Transform | None = None
        self._full_play_xf: sc.Transform | None = None
        self._detail_play_line: sc.Line | None = None
        self._lens_mesh: sc.PolygonMesh | None = None
        self._lens_edge_a: sc.Line | None = None
        self._lens_edge_b: sc.Line | None = None
        self._cell_xfs: list[sc.Transform] = []
        with self._scene_view.scene:
            for y, h, color in (
                (0.0, FULL_H, _CLR_TRACK),
                (FULL_H, LENS_H, _CLR_TRACK),
                (FULL_H + LENS_H, DETAIL_H, _CLR_DETAIL_BG),
            ):
                xf = sc.Transform()
                self._band_xfs.append(xf)
                with xf:
                    sc.Rectangle(1.0, 1.0, color=color)
            self._viewport_xf = sc.Transform()
            with self._viewport_xf:
                sc.Rectangle(1.0, 1.0, color=_CLR_VIEWPORT)
                sc.Rectangle(1.0, 1.0, color=_CLR_EDGE, wireframe=True, thickness=1.5)
            self._full_play_xf = sc.Transform()
            with self._full_play_xf:
                sc.Rectangle(1.0, 1.0, color=_CLR_PLAYHEAD)
            self._detail_play_line = sc.Line([0, 0, 0], [0, 1, 0], color=_CLR_PLAYHEAD, thickness=1.0)
            lens_color = [_LENS_MESH_RGBA[:] for _ in range(4)]
            self._lens_mesh = sc.PolygonMesh(
                [[0.0, 0.0, 0.0] for _ in range(4)],
                lens_color,
                [4],
                [0, 1, 2, 3],
            )
            self._lens_edge_a = sc.Line([0, 0, 0], [0, 0, 0], color=_CLR_EDGE, thickness=1.0)
            self._lens_edge_b = sc.Line([0, 0, 0], [0, 0, 0], color=_CLR_EDGE, thickness=1.0)
            for _ in range(CELL_POOL):
                xf = sc.Transform()
                self._cell_xfs.append(xf)
                with xf:
                    sc.Rectangle(1.0, 1.0, color=_CLR_FRAME)

    @property
    def scene_view(self) -> sc.SceneView:
        return self._scene_view

    def sync(self, view: TimelineView, playhead: int, *, clip_ready: bool) -> None:
        w = view.width_px
        self._width_px = w
        if w < 1.0 or not clip_ready:
            self._set_hidden(True)
            return
        self._set_hidden(False)
        for i, (y, h, _c) in enumerate(
            (
                (0.0, FULL_H, _CLR_TRACK),
                (FULL_H, LENS_H, _CLR_TRACK),
                (FULL_H + LENS_H, DETAIL_H, _CLR_DETAIL_BG),
            )
        ):
            self._band_xfs[i].transform = _xf_rect(0.0, y, w, h, w)

        left, vp_w = view.overview_viewport(w)
        if self._viewport_xf is not None:
            if vp_w >= 1.0:
                self._viewport_xf.visible = True
                self._viewport_xf.transform = _xf_rect(left, 0.0, vp_w, FULL_H, w)
            else:
                self._viewport_xf.visible = False

        ph_full = view.overview_x_at_frame(playhead, w)
        if self._full_play_xf is not None:
            if 0.0 <= ph_full <= w:
                self._full_play_xf.visible = True
                self._full_play_xf.transform = _xf_rect(ph_full, 0.0, 1.0, FULL_H, w)
            else:
                self._full_play_xf.visible = False

        vleft = left
        vright = left + vp_w
        y0 = FULL_H
        y1 = FULL_H + LENS_H
        if self._lens_mesh is not None:
            pts = [
                _scene_point(vleft, y0, w),
                _scene_point(vright, y0, w),
                _scene_point(w, y1, w),
                _scene_point(0.0, y1, w),
            ]
            self._lens_mesh.positions = pts
        if self._lens_edge_a is not None:
            self._lens_edge_a.start = _scene_point(vleft, y0, w)
            self._lens_edge_a.end = _scene_point(0.0, y1, w)
        if self._lens_edge_b is not None:
            self._lens_edge_b.start = _scene_point(vright, y0, w)
            self._lens_edge_b.end = _scene_point(w, y1, w)

        gap_x, _, _ = TimelineView.split_frame_gap(view.x_at_frame(playhead), view.px_per_frame)
        if self._detail_play_line is not None:
            if 0.0 <= gap_x <= w:
                y_top = FULL_H + LENS_H
                y_bot = TOTAL_H
                self._detail_play_line.visible = True
                self._detail_play_line.start = _scene_point(gap_x, y_top, w)
                self._detail_play_line.end = _scene_point(gap_x, y_bot, w)
            else:
                self._detail_play_line.visible = False

        cells = view.detail_cells_grouped(CELL_POOL)
        detail_y = FULL_H + LENS_H
        limit = int(math.ceil(w))
        for i, xf in enumerate(self._cell_xfs):
            if i >= len(cells):
                xf.visible = False
                continue
            _start, _n, x, width = cells[i]
            _gap, body_x, body_w = TimelineView.split_frame_gap(x, width)
            if body_x < 0:
                body_w += body_x
                body_x = 0.0
            if body_x + body_w > limit:
                body_w = float(limit) - body_x
            if body_w < 1.0:
                xf.visible = False
                continue
            xf.visible = True
            xf.transform = _xf_rect(body_x, detail_y, body_w, DETAIL_H, w)

    def _set_hidden(self, hidden: bool) -> None:
        for xf in self._band_xfs:
            xf.visible = not hidden
        for xf in self._cell_xfs:
            xf.visible = not hidden
        for obj in (
            self._viewport_xf,
            self._full_play_xf,
            self._detail_play_line,
            self._lens_mesh,
            self._lens_edge_a,
            self._lens_edge_b,
        ):
            if obj is not None:
                obj.visible = not hidden
