# SPDX-License-Identifier: MIT
"""Timeline ruler and overview view math (PLAN_05 / PLAN_06)."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


def _load_timeline_view():
    root = pathlib.Path(__file__).resolve().parents[5]
    path = root / "source/extensions/v1d.tl/python/v1d/tl/view.py"
    spec = importlib.util.spec_from_file_location("v1d_tl_view_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_tl_view = _load_timeline_view()
TimelineView = _tl_view.TimelineView
clip_edge_zone = _tl_view.clip_edge_zone
next_wheel_zoom_percent = _tl_view.next_wheel_zoom_percent
wheel_zoom_direction = _tl_view.wheel_zoom_direction


class TestWheelZoomPercent(unittest.TestCase):
    def test_wheel_steps_down_five_percent_ladder(self) -> None:
        pct = 100.0
        for expected in (95.0, 90.0, 85.0, 80.0):
            nxt = next_wheel_zoom_percent(pct, True, lo_pct=5.0)
            self.assertEqual(nxt, expected)
            pct = expected

    def test_wheel_steps_up_to_full(self) -> None:
        nxt = next_wheel_zoom_percent(90.0, False, lo_pct=5.0)
        self.assertEqual(nxt, 95.0)
        nxt = next_wheel_zoom_percent(95.0, False, lo_pct=5.0)
        self.assertEqual(nxt, 100.0)

    def test_repeating_scroll_level_keeps_stepping(self) -> None:
        """Same SCROLL_UP reading on every notch must still zoom in again."""
        prev_up, prev_down = 0.0, 0.0
        directions = []
        for _ in range(4):
            directions.append(wheel_zoom_direction(1.0, 0.0, prev_up, prev_down))
            prev_up, prev_down = 1.0, 0.0
        self.assertEqual(directions, [True, True, True, True])
        self.assertFalse(wheel_zoom_direction(0.0, 1.0, prev_up, prev_down))
        self.assertIsNone(wheel_zoom_direction(0.0, 0.0, 1.0, 0.0))

    def test_cumulative_scroll_uses_delta(self) -> None:
        self.assertTrue(wheel_zoom_direction(1.0, 0.0, 0.0, 0.0))
        self.assertTrue(wheel_zoom_direction(2.0, 0.0, 1.0, 0.0))
        self.assertFalse(wheel_zoom_direction(2.0, 1.0, 2.0, 0.0))

    def test_five_percent_ladder_on_twenty_second_clip(self) -> None:
        v = TimelineView(600, 900)
        v.set_fps(30)
        self.assertAlmostEqual(v.min_zoom_percent(), 5.0, delta=0.05)
        pct = v.zoom_percent()
        seen = [round(pct)]
        for _ in range(30):
            target = next_wheel_zoom_percent(pct, True, lo_pct=v.min_zoom_percent())
            if target is None:
                break
            v.set_zoom_percent(target, 0, center=True)
            pct = v.zoom_percent()
            seen.append(round(pct))
        self.assertEqual(seen, list(range(100, 4, -5)))

    def test_wheel_near_max_zoom_no_round_snap_stuck(self) -> None:
        lo = 93.75
        nxt = next_wheel_zoom_percent(94.0, True, lo_pct=lo)
        self.assertAlmostEqual(nxt, lo)
        self.assertIsNone(next_wheel_zoom_percent(lo, True, lo_pct=lo))
        self.assertEqual(next_wheel_zoom_percent(lo, False, lo_pct=lo), 100.0)


class TestTimelineView(unittest.TestCase):
    def test_fit_100_frames_200px(self) -> None:
        v = TimelineView(100, 200)
        self.assertEqual(v.px_per_frame, 2.0)
        self.assertEqual(v.origin, 0.0)
        self.assertEqual(v.pan_max(), 0.0)

    def test_zoom_in_twice_anchor_frame_50(self) -> None:
        v = TimelineView(100, 200)
        v.set_fps(1.0)
        anchor_x_before = v.x_at_frame(50)
        v.zoom(2.0, 50)
        self.assertEqual(v.px_per_frame, 4.0)
        self.assertAlmostEqual(v.x_at_frame(50), anchor_x_before)
        v.zoom(2.0, 50)
        self.assertEqual(v.px_per_frame, 8.0)
        self.assertAlmostEqual(v.x_at_frame(50), anchor_x_before)

    def test_zoom_out_past_fit(self) -> None:
        v = TimelineView(100, 200)
        px_min = v.px_per_frame
        v.zoom(0.5, 0)
        self.assertEqual(v.px_per_frame, px_min)

    def test_set_zoom_percent_steps(self) -> None:
        v = TimelineView(600, 600)
        self.assertAlmostEqual(v.zoom_percent(), 100.0)
        v.set_zoom_percent(95.0, 0)
        self.assertAlmostEqual(v.zoom_percent(), 95.0, delta=0.6)
        v.set_zoom_percent(90.0, 0)
        self.assertAlmostEqual(v.zoom_percent(), 90.0, delta=0.6)

    def test_set_zoom_percent_centers_anchor_frame(self) -> None:
        v = TimelineView(100, 200)
        v.set_zoom_percent(50.0, 40, center=True)
        self.assertAlmostEqual(v.x_at_frame(40), v.width_px * 0.5, delta=0.6)

    def test_clip_rect_matches_frame_scale_at_every_zoom(self) -> None:
        """600-frame media (0..599) stays 600 frames wide on the ruler at every zoom."""
        v = TimelineView(1200, 1090)
        for pct in (100.0, 95.0, 70.0, 40.0, 10.0):
            v.set_zoom_percent(pct, 0)
            x0, w = v.clip_rect_px(0, 599)
            self.assertEqual(x0, int(round(v.x_at_frame(0))))
            self.assertEqual(x0 + w, int(round(v.x_at_frame(600))))
            self.assertAlmostEqual(w / v.px_per_frame, 600.0, delta=1.5)

    def test_frame_gap_x_past_cell_pool(self) -> None:
        v = TimelineView(500, 400)
        v.px_per_frame = 2.0
        v.origin = 0.0
        cells = v.detail_grid(16)
        self.assertLess(len(cells), 200)
        self.assertEqual(v.frame_gap_x(220), 220 * v.layout_pitch_px())
        self.assertIsNone(v.gap_x_for_frame(220, cells))

    def test_short_clip_no_zoom_in_past_px_max(self) -> None:
        v = TimelineView(10, 900)
        self.assertGreater(v.px_min(), 48.0)
        before = v.px_per_frame
        v.zoom(2.0, 5)
        self.assertEqual(v.px_per_frame, before)

    def test_frame_at_x_clamped(self) -> None:
        v = TimelineView(100, 200)
        self.assertEqual(v.frame_at_x(-1000), 0)
        self.assertEqual(v.frame_at_x(100000), v.frame_max)

    def test_tick_step_and_ticks(self) -> None:
        v = TimelineView(100, 800)
        v.px_per_frame = 10.0
        v.origin = 0.0
        self.assertEqual(v.tick_step(), 10)
        ticks = v.visible_ticks()
        self.assertIn(0, ticks)
        for t in ticks:
            x = v.x_at_frame(t)
            self.assertGreaterEqual(x, 0.0)
            self.assertLessEqual(x, v.width_px)

    def test_follow_playhead_left_of_view(self) -> None:
        v = TimelineView(200, 800)
        v.px_per_frame = 10.0
        v.origin = 150.0
        self.assertLess(v.x_at_frame(100), 0.0)
        v.follow(100, 1)
        self.assertAlmostEqual(v.x_at_frame(100), 0.2 * v.width_px)

    def test_follow_after_slide_aligns_left_edge_once(self) -> None:
        v = TimelineView(200, 800)
        v.px_per_frame = 10.0
        v.origin = 40.0
        v.align_on_play = True
        v.follow(50, 1)
        self.assertAlmostEqual(v.x_at_frame(50), 0.0)
        self.assertFalse(v.align_on_play)
        origin = v.origin
        v.follow(51, 1)
        self.assertEqual(v.origin, origin)

    def test_follow_forward_pages_when_playhead_passes_the_right_edge(self) -> None:
        v = TimelineView(200, 800)
        v.px_per_frame = 10.0
        v.origin = 0.0
        edge = v.frame_at_x(v.width_px)
        v.follow(edge, 1)
        self.assertEqual(v.origin, 0.0)
        v.follow(edge + 1, 1)
        self.assertAlmostEqual(v.x_at_frame(edge + 1), 0.0)
        origin = v.origin
        v.follow(edge + 2, 1)
        self.assertEqual(v.origin, origin)

    def test_follow_reverse_pages_when_playhead_passes_the_left_edge(self) -> None:
        v = TimelineView(200, 800)
        v.px_per_frame = 10.0
        v.origin = 100.0
        v.follow(99, -1)
        self.assertAlmostEqual(v.x_at_frame(99), v.width_px)
        origin = v.origin
        v.follow(98, -1)
        self.assertEqual(v.origin, origin)

    def test_overview_fit(self) -> None:
        v = TimelineView(100, 200)
        left, width = v.overview_viewport(400.0)
        self.assertAlmostEqual(left, 0.0)
        self.assertAlmostEqual(width, 400.0)

    def test_overview_zoom_once_anchor_50(self) -> None:
        v = TimelineView(100, 200)
        v.zoom(2.0, 50)
        self.assertEqual(v.px_per_frame, 4.0)
        ow = 400.0
        left, width = v.overview_viewport(ow)
        self.assertAlmostEqual(width, ow / 2.0)
        x50 = v.overview_x_at_frame(50, 400.0)
        self.assertGreaterEqual(x50, left)
        self.assertLessEqual(x50, left + width)

    def test_overview_origin_25(self) -> None:
        v = TimelineView(100, 200)
        v.zoom(2.0, 0)  # pan room before origin can move off 0
        v.set_origin(25.0)
        ow = 400.0
        self.assertAlmostEqual(v.overview_x_at_frame(25, ow), 100.0)
        left, _ = v.overview_viewport(ow)
        self.assertAlmostEqual(left, 100.0)

    def test_split_frame_gap_leaves_one_pixel(self) -> None:
        gap, body_x, body_w = TimelineView.split_frame_gap(0.0, 8.0)
        self.assertEqual((gap, body_x, body_w), (0, 1, 7))
        gap, body_x, body_w = TimelineView.split_frame_gap(8.0, 8.0)
        self.assertEqual((gap, body_x, body_w), (8, 9, 7))
        _gap, _body_x, body_w = TimelineView.split_frame_gap(0.0, 1.2)
        self.assertEqual(body_w, 0)

    def test_detail_cells_one_frame_each_at_fit(self) -> None:
        v = TimelineView(10, 100)
        cells = v.detail_cells(64)
        self.assertEqual([c[0] for c in cells], list(range(10)))
        self.assertAlmostEqual(cells[0][2], 10.0)
        self.assertAlmostEqual(cells[4][1], 40.0)

    def test_overview_cells_tile_full_width(self) -> None:
        v = TimelineView(10, 100)
        cells = v.overview_cells(100.0, 64)
        self.assertEqual(len(cells), 10)
        self.assertAlmostEqual(sum(c[2] for c in cells), 100.0)
        self.assertAlmostEqual(cells[0][1], 0.0)

    def test_overview_viewport_shrinks_when_zoomed_in(self) -> None:
        v = TimelineView(100, 200)
        ow = 400.0
        _, w_fit = v.overview_viewport(ow)
        self.assertAlmostEqual(w_fit, ow)
        v.zoom(2.0, 0)
        _, w_zoom = v.overview_viewport(ow)
        self.assertAlmostEqual(w_zoom, ow / 2.0)

    def test_overview_frame_pitch_fills_width(self) -> None:
        v = TimelineView(100, 200)
        ow = 400.0
        fw = v.overview_frame_body_width(ow)
        self.assertAlmostEqual(100.0 * fw + 99.0, ow)
        self.assertAlmostEqual(v.overview_x_at_frame(0, ow), 0.0)
        self.assertAlmostEqual(v.overview_divider_x(0, ow), fw)

    def test_overview_fit_after_zoom(self) -> None:
        v = TimelineView(100, 200)
        v.zoom(2.0, 0)
        v.fit()
        left, width = v.overview_viewport(400.0)
        self.assertAlmostEqual(width, 400.0)

    def test_zoom_to_span_anchor_left(self) -> None:
        v = TimelineView(100, 200)
        v.origin = 10.0
        v.zoom_to_span(50.0, 0, "left")
        self.assertAlmostEqual(v.origin, 10.0)

    def test_zoom_to_span_anchor_right(self) -> None:
        v = TimelineView(100, 200)
        right = v.right_edge_frame()
        v.zoom_to_span(50.0, int(right), "right")
        self.assertAlmostEqual(v.right_edge_frame(), right, delta=0.5)

    def test_zoom_to_span_clamps_px_max(self) -> None:
        v = TimelineView(100, 200)
        v.zoom_to_span(0.5, 0, "left")
        self.assertAlmostEqual(v.px_per_frame, v.px_max())

    def test_frames_per_cell_one_at_max_zoom(self) -> None:
        v = TimelineView(100, 200)
        v.px_per_frame = 48.0
        self.assertEqual(v.frames_per_cell(), 1)

    def test_frames_per_cell_groups_when_narrow(self) -> None:
        v = TimelineView(600, 960)
        v.fit()
        self.assertGreater(v.frames_per_cell(), 1)

    def test_detail_cells_grouped_cap_on_gop30_fit(self) -> None:
        v = TimelineView(600, 960)
        v.fit()
        cells = v.detail_cells_grouped(128)
        self.assertLessEqual(len(cells), 128)
        self.assertGreater(v.frames_per_cell(), 1)
        for start, n, _x, w in cells:
            self.assertGreaterEqual(n, 1)
            self.assertGreaterEqual(w, 2.0)

    def test_detail_grid_even_pitch_at_max_zoom(self) -> None:
        v = TimelineView(600, 960)
        v.px_per_frame = 48.0
        v.origin = 0.0
        cells = v.detail_grid(128)
        self.assertGreaterEqual(len(cells), 2)
        pitch = cells[0][3]
        self.assertEqual(pitch, 48)
        for i in range(1, len(cells)):
            self.assertEqual(cells[i][2] - cells[i - 1][2], pitch)
            self.assertEqual(cells[i][1], 1)
        self.assertEqual(v.gap_x_for_frame(0, cells), cells[0][2])
        self.assertEqual(v.gap_x_for_frame(1, cells), cells[1][2])

    def test_max_zoom_is_one_second_and_survives_resize(self) -> None:
        v = TimelineView(600, 900)
        v.set_fps(30)
        v.zoom(1000.0, 0)
        self.assertAlmostEqual(v.width_px / v.px_per_frame, 30.0, delta=0.05)
        v.set_width_px(1500)
        self.assertAlmostEqual(v.width_px / v.px_per_frame, 30.0, delta=0.05)

    def test_grid_hidden_until_one_white_and_one_dark(self) -> None:
        v = TimelineView(600, 960)
        v.fit()
        self.assertFalse(v.grid_visible())
        self.assertEqual(v.detail_grid(128), [])
        v.px_per_frame = 2.0
        self.assertTrue(v.grid_visible())
        cells = v.detail_grid(1024)
        self.assertGreaterEqual(len(cells), 2)
        self.assertEqual(cells[0][3], 2)
        self.assertEqual(cells[1][2] - cells[0][2], 2)


class TestClipEdgeZone(unittest.TestCase):
    def test_ends_trim_and_middle_moves(self) -> None:
        self.assertEqual(clip_edge_zone(4, 0, 400), "trim_left")
        self.assertEqual(clip_edge_zone(200, 0, 400), "body")
        self.assertEqual(clip_edge_zone(395, 0, 400), "trim_right")
        self.assertEqual(clip_edge_zone(401, 0, 400), "trim_right")
        self.assertEqual(clip_edge_zone(420, 0, 400), "outside")

    def test_scrolled_off_edge_is_not_a_trim(self) -> None:
        self.assertEqual(
            clip_edge_zone(5, -80, 400, left_visible=False, right_visible=True),
            "body",
        )
        self.assertEqual(
            clip_edge_zone(300, 0, 400, left_visible=True, right_visible=False),
            "body",
        )


if __name__ == "__main__":
    unittest.main()
