# SPDX-License-Identifier: MIT
"""Timeline window. Step 3: viewport on the full band."""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import carb
import carb.input
import omni.appwindow
import omni.ext
import omni.kit.app
import omni.ui as ui
from omni.kit.menu.utils import MenuHelperExtension
from omni.ui import color as cl

from v1d.kit.window_menu import unwire_window_menu, wire_window_menu
from v1d.ngn.fixtures import S4_FIXTURE_CHOICES, fixture_index_for_path, fixture_path
from v1d.ngn.session import ScrubSession
from v1d.tl.sequence import MAX_TRACKS, Clip, Sequence
from v1d.tl.view import (
    TimelineView,
    clip_edge_zone,
    clip_trim_edge_px,
    next_wheel_zoom_percent,
    wheel_zoom_direction,
)

WINDOW_TITLE = "Timeline"
ROW_H = 24
STACK_SPACING = 4
FULL_H = 28
LENS_H = 28
DETAIL_H = 64
_TRACK_DIVIDER_H = 1
RULER_H = 18
COLUMN_W = 112
DEFAULT_TRACK_ROWS = 2
_MOUSE_LEFT = int(carb.input.MouseInput.LEFT_BUTTON)
_MOUSE_RIGHT = int(carb.input.MouseInput.RIGHT_BUTTON)


def _drop_path(raw: str) -> str:
    """Plain path from a drop payload (accepts file:// URIs too)."""
    s = raw.strip()
    if s.startswith("file://"):
        return unquote(urlparse(s).path)
    return s


def _detail_strip_h(track_rows: int) -> int:
    n = max(1, int(track_rows))
    return DETAIL_H * n + _TRACK_DIVIDER_H * max(0, n - 1)


def _track_pane_h(track_rows: int) -> int:
    return RULER_H + _detail_strip_h(track_rows)


def _time_pane_h(track_rows: int) -> int:
    return LENS_H + _track_pane_h(track_rows)
_ICON_DIR = Path(__file__).resolve().parent / "icons"


def _transport_icon(name: str, tip: str, clicked) -> ui.Button:
    return ui.Button(
        "",
        width=28,
        height=28,
        image_url=str(_ICON_DIR / f"{name}.svg"),
        image_width=14,
        image_height=14,
        tooltip=tip,
        clicked_fn=clicked,
    )


_TOGGLE_ON_STYLE = {"background_color": 0xFF00FFFF, "border_radius": 3}


def _transport_toggle(name: str, tip: str, clicked) -> ui.Button:
    return ui.Button(
        "",
        width=28,
        height=28,
        image_url=str(_ICON_DIR / f"{name}.svg"),
        image_width=14,
        image_height=14,
        tooltip=tip,
        clicked_fn=clicked,
    )
_EDGE_PX = 14


def _is_space_key(key) -> bool:
    if key == carb.input.KeyboardInput.SPACE or key == " ":
        return True
    try:
        return int(key) == int(carb.input.KeyboardInput.SPACE)
    except (TypeError, ValueError):
        return False

def _png_rgba(width: int, height: int, rgba: bytes) -> bytes:
    import struct
    import zlib

    raw = b"".join(b"\x00" + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def _hand_png(rows: tuple[str, ...]) -> bytes:
    """24x24 PNG. B = outline, S = skin, . = clear."""
    width = 24
    height = 24
    pixels = bytearray(width * height * 4)
    for y, row in enumerate(rows[:height]):
        row = row.ljust(width, ".")[:width]
        for x, ch in enumerate(row):
            i = (y * width + x) * 4
            if ch == "B":
                pixels[i:i + 4] = b"\x14\x14\x14\xff"
            elif ch == "S":
                pixels[i:i + 4] = b"\xff\xdc\xb4\xff"
    return _png_rgba(width, height, bytes(pixels))


def _xcursor_png(path: str, target: int = 24) -> bytes | None:
    """Largest theme cursor image near ``target`` px, as PNG."""
    import struct
    from pathlib import Path

    data = Path(path).read_bytes()
    if data[:4] != b"Xcur":
        return None
    ntoc = struct.unpack_from("<I", data, 12)[0]
    best: tuple[int, int, int, int, tuple[int, ...]] | None = None
    for i in range(ntoc):
        typ, _sub, pos = struct.unpack_from("<3I", data, 16 + i * 12)
        if typ != 0xFFFD0002:
            continue
        header, _ctype, _csub, _cver, w, h, xhot, yhot, _delay = struct.unpack_from("<9I", data, pos)
        pixels = struct.unpack_from(f"<{w * h}I", data, pos + header)
        rank = abs(int(w) - target)
        if best is None or rank < best[0]:
            best = (rank, w, h, xhot, yhot, pixels)
    if best is None:
        return None
    _rank, w, h, _xhot, _yhot, pixels = best
    rgba = bytearray(w * h * 4)
    for i, p in enumerate(pixels):
        rgba[i * 4 + 0] = (p >> 16) & 255
        rgba[i * 4 + 1] = (p >> 8) & 255
        rgba[i * 4 + 2] = p & 255
        rgba[i * 4 + 3] = (p >> 24) & 255
    return _png_rgba(w, h, bytes(rgba))


def _theme_cursor_path(name: str) -> str | None:
    import pathlib
    import subprocess

    theme = "Yaru"
    try:
        theme = subprocess.check_output(
            ["gsettings", "get", "org.gnome.desktop.interface", "cursor-theme"],
            text=True,
        ).strip().strip("'\"")
    except Exception:
        pass
    aliases = {
        "grab": ("grab", "hand1"),
        "grabbing": ("grabbing", "closedhand"),
        "ew-resize": ("ew-resize", "col-resize", "size_hor"),
    }
    folders = [
        pathlib.Path.home() / ".icons" / theme / "cursors",
        pathlib.Path("/usr/share/icons") / theme / "cursors",
        pathlib.Path("/usr/share/icons/Adwaita/cursors"),
    ]
    for folder in folders:
        for alias in aliases[name]:
            path = folder / alias
            if path.exists():
                return str(path)
    return None


_OPEN_HAND = (
    "BB......................",
    "BSSB....................",
    "BSSB.BB.................",
    "BSSBBSSB................",
    "BSSBBSSB.BB.............",
    "BSSBBSSBBSSB............",
    "BSSBBSSBBSSB............",
    ".BSSBSSBSSB.............",
    "..BSSSSSSB..............",
    "...BSSSSB...............",
    "....BBB.................",
)
_GRAB_HAND = (
    "..BBBBBB................",
    ".BSSSSSSB...............",
    "BSSBBBBSSB..............",
    "BSSB..BSSSB.............",
    "BSSB..BSSSB.............",
    ".BSBBBBSSB..............",
    "..BSSSSSB...............",
    "..BSSSSSB...............",
    "...BBBBB................",
)
_EW_ARROW = (
    "...........BB...........",
    "..........B..B..........",
    ".........B....B.........",
    "........B......B........",
    ".......B........B.......",
    "BBBBBBBBBBBBBBBBBBBBBBBB",
    ".......B........B.......",
    "........B......B........",
    ".........B....B.........",
    "..........B..B..........",
    "...........BB...........",
)
_VIEWPORT_STYLE = {
    "background_color": cl(0.0, 0.85, 0.95, 1.0),
    "border_color": cl(1.0, 1.0, 1.0, 1.0),
    "border_width": 2,
    "margin_height": 4,
}
_FRAME_STYLE = {"background_color": cl(0.08, 0.08, 0.08, 1.0)}
_GAP_STYLE = {"background_color": cl(1.0, 1.0, 1.0, 1.0)}
_PLAYHEAD_STYLE = {"background_color": cl(1.0, 0.0, 1.0, 1.0)}
_PLAYHEAD_TRI_H = 10
_PLAYHEAD_TRI_W = 10
_LENS_STYLE = {"background_color": cl(0.15, 0.75, 0.9, 0.55)}
_CLIP_STYLE = {"background_color": cl(0.22, 0.45, 0.72, 1.0)}
_CLIP_OFF_STYLE = {"background_color": cl(0.22, 0.45, 0.72, 0.35)}
_CLIP_SELECTED_STYLE = {
    "background_color": cl(0.22, 0.45, 0.72, 1.0),
    "border_color": cl(1.0, 0.85, 0.2, 1.0),
    "border_width": 2,
}
_CLIP_EDGE_STYLE = {"background_color": cl(0.92, 0.95, 1.0, 1.0)}
_CLEAR = {"background_color": 0x00000000}
_COLUMN_BG = {"background_color": cl(0.16, 0.16, 0.16, 1.0)}
_COLUMN_LABEL = {"font_size": 13, "color": 0xFFE6E6E6}
_TRACK_DIVIDER_STYLE = {"background_color": cl(0.45, 0.45, 0.45, 1.0)}
_CELL_POOL = 1024
_RULER_TICKS = 32
_CLIP_TRIM_PX = 10
_CLIP_POOL_PER_ROW = 4
_CLIP_DRAG_SOURCE_STYLE = {"background_color": cl(0.22, 0.45, 0.72, 0.35)}
_CLIP_MISSING_STYLE = {"background_color": cl(0.72, 0.18, 0.18, 1.0)}
_TRACK_DROP_STYLE = {"background_color": cl(0.15, 0.75, 0.9, 0.18)}
_GHOST_OK_STYLE = {"background_color": cl(0.22, 0.75, 0.85, 0.55)}
_GHOST_NUDGE_STYLE = {"background_color": cl(0.95, 0.7, 0.15, 0.55)}
_GHOST_NO_ROOM_STYLE = {"background_color": cl(0.85, 0.2, 0.2, 0.45)}
_STRIP_WIDTH_EPS = 2.0
_WHEEL_ZOOM_STEP_PCT = 5.0
_WHEEL_ZOOM_MIN_S = 0.05
_ZOOM_PERCENT_SETTING = "/persistent/exts/v1d.tl/zoom_percent"
_TRACK_COUNT_SETTING = "/persistent/exts/v1d.tl/track_count"


class V1dTimelineExtension(omni.ext.IExt, MenuHelperExtension):
    def on_startup(self, ext_id: str):
        self._closed = False
        self._drop_sub = None
        try:
            self._drop_sub = (
                omni.appwindow.get_default_app_window()
                .get_window_drop_event_stream()
                .create_subscription_to_pop(self._on_window_drop, name="v1d.tl.window_drop")
            )
        except Exception as exc:  # noqa: BLE001
            carb.log_warn(f"[v1d.tl] window drop stream unavailable: {exc!r}")
        self._wheel_at = 0.0
        self._wheel_up = 0.0
        self._wheel_down = 0.0
        self._full_drag: str | None = None
        self._full_grab = 0.0
        self._resize_anchor_frame = 0.0
        self._resize_right_px = 0.0
        self._resize_left_px = 0.0
        self._vp_sig: tuple[float, float, float] | None = None
        self._view = TimelineView()
        settings = carb.settings.get_settings()
        title = str(settings.get("/exts/v1d.tl/window_title") or WINDOW_TITLE)
        self._session = ScrubSession.get()
        self._strip_frame: ui.Frame | None = None
        self._pan_lead: ui.Spacer | None = None
        self._pan_thumb: ui.ZStack | None = None
        self._pan_tail: ui.Spacer | None = None
        self._full_input: ui.Rectangle | None = None
        self._cursor_kind = "arrow"
        self._hand_ready = False
        self._kb_sub = None
        self._kb_device = None
        self._grid_sig: tuple[object, ...] | None = None
        self._cell_gaps: list[list[ui.Rectangle]] = []
        self._cell_bodies: list[list[ui.Rectangle]] = []
        self._cell_fracs: list[float] = []
        self._grid_leads: list[ui.Spacer | None] = []
        self._grid_tails: list[ui.Spacer | None] = []
        self._clock: ui.Label | None = None
        self._ruler_frame: ui.Frame | None = None
        self._grid_cells: list[tuple[int, int, int, int]] = []
        self._full_play_lead: ui.Spacer | None = None
        self._full_play_tail: ui.Spacer | None = None
        self._detail_play_frame: ui.Frame | None = None
        self._play_btn: ui.Button | None = None
        self._reverse_btn: ui.Button | None = None
        self._scissor_btn: ui.Button | None = None
        self._clock_btn: ui.Button | None = None
        self._stretch_mode = False
        self._project_path: str | None = None
        self._dirty_baseline = 0
        self._blink_sig: tuple[int, int] | None = None
        self._lens_leads: list[ui.Spacer] = []
        self._lens_bodies: list[ui.Rectangle] = []
        self._lens_tails: list[ui.Spacer] = []
        self._lens_line_l = None
        self._lens_line_r = None
        self._detail_drag = False
        self._sequence: Sequence | None = None
        self._clip_drag: tuple[str, int, str, object, float] | None = None
        self._clip_drag_moved = False
        self._playhead_drag = False
        self._playhead_grab_dx = 0.0
        self._playhead_mark_x: int | None = None
        self._play_head_frame: ui.Frame | None = None
        self._layout_refresh_depth = 0
        self._track_clip_leads: list[ui.Rectangle | None] = []
        self._track_clip_tails: list[ui.Spacer | None] = []
        self._track_clip_bodies: list[ui.Rectangle | None] = []
        self._track_clip_labels: list[ui.Label | None] = []
        self._track_clip_label_leads: list[ui.Rectangle | None] = []
        self._track_clip_edge_leads: list[ui.Rectangle | None] = []
        self._track_clip_edge_gaps: list[ui.Rectangle | None] = []
        self._track_clip_edge_l: list[ui.Rectangle | None] = []
        self._track_clip_edge_r: list[ui.Rectangle | None] = []
        self._clip_slots: list[list[dict[str, object]]] = []
        self._track_drop_hilite: list[ui.Rectangle] = []
        self._track_ghost_leads: list[ui.Rectangle] = []
        self._track_ghost_bodies: list[ui.Rectangle] = []
        self._move_drag_dest: int | None = None
        self._move_feedback_sig: object = None
        self._move_drag_snap: Clip | None = None
        self._track_titles: list[ui.Label] = []
        self._track_eyes: list[ui.Button] = []
        self._track_speakers: list[ui.Button] = []
        self._header_drag: tuple[int, float] | None = None
        self._status: ui.Label | None = None
        self._zoom_label: ui.Label | None = None
        self._track_menu: ui.Menu | None = None
        self._track_menu_track = 0
        self._track_menu_insert_above = False
        self._detail_strip_zstack: ui.ZStack | None = None
        self._time_pane_hstack: ui.HStack | None = None
        self._track_rows_frame: ui.Frame | None = None
        self._track_header_frame: ui.Frame | None = None

        self._window = ui.Window(
            title,
            width=960,
            height=FULL_H + _time_pane_h(DEFAULT_TRACK_ROWS) + 4 * (ROW_H + STACK_SPACING),
        )
        self._window.frame.clear()
        with self._window.frame:
            with ui.VStack(spacing=STACK_SPACING, mouse_wheel_fn=self._on_wheel):
                with ui.HStack(height=ROW_H):
                    ui.Label("Clip:", width=40)
                    self._path_field = ui.StringField()
                    ui.Button("Open", width=60, clicked_fn=self._on_open_clicked)
                with ui.HStack(height=ROW_H):
                    ui.Label("S4:", width=40)
                    labels = [label for _, label in S4_FIXTURE_CHOICES]
                    self._fixture_combo = ui.ComboBox(0, *labels, width=ui.Fraction(1))
                with ui.HStack(height=ROW_H, spacing=4):
                    self._clock = ui.Label(
                        "00h:00m:00s:00f",
                        width=148,
                        style={"font_size": 14, "color": 0xFFE6E6E6},
                    )
                    ui.Spacer(width=ui.Fraction(1))
                    self._scissor_btn = _transport_icon("scissor", "Cut at playhead", self._on_scissor)
                    self._clock_btn = _transport_toggle(
                        "clock", "Timestretch mode", self._on_stretch_toggle
                    )
                    ui.Rectangle(width=1, height=20, style={"background_color": 0xFF3A3A3A})
                    _transport_icon("start", "Start", self._on_start)
                    _transport_icon("prev-frame", "Previous frame", lambda: self._on_step(-1))
                    self._reverse_btn = _transport_icon("reverse-play", "Reverse", lambda: self._on_play(-1))
                    _transport_icon("stop", "Stop", self._on_stop)
                    _transport_icon("pause", "Pause", self._on_pause)
                    self._play_btn = _transport_icon("play", "Play", lambda: self._on_play(1))
                    _transport_icon("next-frame", "Next frame", lambda: self._on_step(1))
                    _transport_icon("end", "End", self._on_end)
                    ui.Spacer(width=ui.Fraction(1))
                    ui.Spacer(width=148)
                with ui.HStack(height=ROW_H, spacing=4):
                    ui.Button("Zoom −", width=56, clicked_fn=lambda: self._on_zoom(0.5))
                    ui.Button("Zoom +", width=56, clicked_fn=lambda: self._on_zoom(2.0))
                    ui.Button("Fit", width=40, clicked_fn=self._on_fit)
                    self._zoom_label = ui.Label("100%", width=72)
                with ui.HStack(spacing=0, height=ui.Pixel(FULL_H)):
                    with ui.ZStack(width=ui.Pixel(COLUMN_W), height=ui.Pixel(FULL_H)):
                        ui.Rectangle(
                            width=ui.Pixel(COLUMN_W),
                            height=ui.Pixel(FULL_H),
                            style=_COLUMN_BG,
                        )
                        ui.Label(
                            "Overview",
                            alignment=ui.Alignment.CENTER,
                            style=_COLUMN_LABEL,
                        )
                    with ui.Frame(
                        width=ui.Fraction(1),
                        height=ui.Pixel(FULL_H),
                        horizontal_clipping=True,
                        vertical_clipping=True,
                    ):
                        with ui.ZStack(height=ui.Pixel(FULL_H)):
                            ui.Rectangle(
                                height=ui.Pixel(FULL_H),
                                style={"background_color": 0xFFC8C8C8},
                                opaque_for_mouse_events=False,
                            )
                            with ui.HStack(height=ui.Pixel(FULL_H)):
                                self._pan_lead = ui.Spacer(width=ui.Fraction(0))
                                self._pan_thumb = ui.ZStack(
                                    width=ui.Fraction(1),
                                    height=ui.Pixel(FULL_H),
                                )
                                with self._pan_thumb:
                                    ui.Rectangle(
                                        width=ui.Fraction(1),
                                        height=ui.Pixel(FULL_H),
                                        style=_VIEWPORT_STYLE,
                                        opaque_for_mouse_events=False,
                                    )
                                self._pan_tail = ui.Spacer(width=ui.Fraction(0))
                            with ui.HStack(height=ui.Pixel(FULL_H), spacing=0):
                                self._full_play_lead = ui.Spacer(width=ui.Fraction(0))
                                ui.Rectangle(
                                    width=ui.Pixel(1),
                                    height=ui.Pixel(FULL_H),
                                    style=_PLAYHEAD_STYLE,
                                    opaque_for_mouse_events=False,
                                )
                                self._full_play_tail = ui.Spacer(width=ui.Fraction(1))
                            self._full_input = ui.Rectangle(
                                width=ui.Fraction(1),
                                height=ui.Pixel(FULL_H),
                                style={"background_color": 0x01000000},
                                opaque_for_mouse_events=True,
                                mouse_pressed_fn=self._on_full_pressed,
                                mouse_moved_fn=self._on_full_moved,
                                mouse_released_fn=self._on_full_released,
                                mouse_hovered_fn=self._on_body_hover,
                            )
                with ui.HStack(
                    spacing=0, height=ui.Pixel(_time_pane_h(DEFAULT_TRACK_ROWS))
                ) as time_pane:
                    self._time_pane_hstack = time_pane
                    self._build_track_column()
                    with ui.Frame(
                        width=ui.Fraction(1),
                        height=ui.Pixel(_time_pane_h(DEFAULT_TRACK_ROWS)),
                        horizontal_clipping=True,
                        vertical_clipping=True,
                    ) as strip_frame:
                        self._strip_frame = strip_frame
                        strip_frame.set_computed_content_size_changed_fn(self._on_strip_width)
                        self._wire_strip_drop(strip_frame)
                        with ui.VStack(spacing=0):
                                with ui.ZStack(height=ui.Pixel(LENS_H)):
                                    with ui.VStack(spacing=0, height=ui.Pixel(LENS_H)):
                                        for _ in range(LENS_H):
                                            with ui.HStack(spacing=0, height=ui.Pixel(1)):
                                                lead = ui.Rectangle(
                                                    width=ui.Fraction(0),
                                                    height=ui.Pixel(1),
                                                    style={"background_color": 0xFFC8C8C8},
                                                    opaque_for_mouse_events=False,
                                                )
                                                body = ui.Rectangle(
                                                    width=ui.Fraction(1),
                                                    height=ui.Pixel(1),
                                                    style=_LENS_STYLE,
                                                    opaque_for_mouse_events=False,
                                                )
                                                tail = ui.Rectangle(
                                                    width=ui.Fraction(0),
                                                    height=ui.Pixel(1),
                                                    style={"background_color": 0xFFC8C8C8},
                                                    opaque_for_mouse_events=False,
                                                )
                                            self._lens_leads.append(lead)
                                            self._lens_bodies.append(body)
                                            self._lens_tails.append(tail)
                                    self._mount_lens_lines()
                                with ui.ZStack(width=ui.Fraction(1), height=ui.Pixel(RULER_H)):
                                    self._ruler_frame = ui.Frame(
                                        width=ui.Fraction(1),
                                        height=ui.Pixel(RULER_H),
                                        build_fn=self._build_ruler,
                                    )
                                    ui.Rectangle(
                                        width=ui.Fraction(1),
                                        height=ui.Pixel(RULER_H),
                                        style={"background_color": 0x01000000},
                                        opaque_for_mouse_events=True,
                                        mouse_pressed_fn=self._on_ruler_pressed,
                                    )
                                    self._play_head_frame = ui.Frame(
                                        width=ui.Fraction(1),
                                        height=ui.Pixel(RULER_H),
                                        build_fn=self._build_play_head,
                                        opaque_for_mouse_events=False,
                                    )
                                with ui.ZStack(
                                    height=ui.Pixel(_detail_strip_h(DEFAULT_TRACK_ROWS))
                                ) as strip_z:
                                    self._detail_strip_zstack = strip_z
                                    self._track_rows_frame = ui.Frame(
                                        width=ui.Fraction(1),
                                        height=ui.Fraction(1),
                                        build_fn=self._build_track_rows,
                                    )
                                    self._detail_play_frame = ui.Frame(
                                        width=ui.Fraction(1),
                                        height=ui.Pixel(_detail_strip_h(DEFAULT_TRACK_ROWS)),
                                        build_fn=self._build_detail_playhead,
                                        opaque_for_mouse_events=False,
                                    )
                self._status = ui.Label("Open a clip")
                self._fixture_combo.model.add_item_changed_fn(self._on_fixture_changed)

        self._window_title = title
        wire_window_menu(self, title, self._window, self._show_window)
        self._register_project_hooks()
        self._session.add_sequence_listener(self._on_session_sequence)
        self._session.add_clip_path_listener(self._apply_clip_path)
        self._sync_ui_from_session()

        stream = omni.kit.app.get_app().get_update_event_stream()
        self._sub = stream.create_subscription_to_pop(self._on_update, name="v1d.tl")
        self._subscribe_space()

    def _subscribe_space(self) -> None:
        iinput = carb.input.acquire_input_interface()
        keyboard = omni.appwindow.get_default_app_window().get_keyboard()
        self._kb_device = keyboard
        self._kb_sub = iinput.subscribe_to_keyboard_events(keyboard, self._on_app_key)

    def _on_app_key(self, event):
        if getattr(self, "_closed", True):
            return True
        inp = event.input
        right = inp == carb.input.KeyboardInput.RIGHT
        left = inp == carb.input.KeyboardInput.LEFT
        if right or left:
            if not self._clip_ready():
                return True
            try:
                et = int(event.type)
            except (TypeError, ValueError):
                return True
            d = 1 if right else -1
            key_press = int(carb.input.KeyboardEventType.KEY_PRESS)
            key_release = int(
                getattr(
                    carb.input.KeyboardEventType,
                    "KEY_RELEASE",
                    getattr(carb.input.KeyboardEventType, "KeyRelease", 2),
                )
            )
            if et == key_press:
                if self._session.arrow_key_down == d:
                    return True
                if self._sequence is not None:
                    ph = self._sequence_playhead()
                    new_seq = max(0, min(self._sequence.sequence_frame_max, ph + d))
                    self._seek_sequence(
                        new_seq,
                        scrub_begin=True,
                        scrub_change=True,
                        scrub_end=True,
                    )
                    self._session.on_arrow_sequence_arm(d, new_seq)
                else:
                    self._session.on_arrow_pressed(d, self._arrow_current_source())
            elif et == key_release:
                self._session.on_arrow_released(d)
                self._refresh_playhead()
            return True
        try:
            if int(event.type) != int(carb.input.KeyboardEventType.KEY_PRESS):
                return True
        except (TypeError, ValueError):
            return True
        if not _is_space_key(inp):
            return True
        self._toggle_play()
        return True

    def _toggle_play(self) -> None:
        session = getattr(self, "_session", None)
        if getattr(self, "_closed", True) or session is None:
            return
        info = session.clip_info
        if not info or int(info.get("frames") or 0) <= 0:
            return
        if session.play_dir != 0:
            session.transport_stop()
        else:
            self._start_transport(1)
        self._refresh_playhead()

    def _show_window(self, visible: bool) -> None:
        self._window.visible = bool(visible)

    def _clip_ready(self) -> bool:
        info = self._session.clip_info
        return bool(info) and int(info.get("frames") or 0) > 0

    def _sequence_playhead(self) -> int:
        if self._sequence is not None:
            return int(self._sequence.playhead)
        return int(self._session.last_request)

    def _timeline_frame_count(self) -> int:
        if self._sequence is not None and self._sequence.timeline_frame_count > 0:
            return int(self._sequence.timeline_frame_count)
        return max(self._view.frame_count, 1)

    def _read_saved_zoom_percent(self) -> float | None:
        raw = carb.settings.get_settings().get(_ZOOM_PERCENT_SETTING)
        if raw is None:
            raw = carb.settings.get_settings().get("/exts/v1d.tl/zoom_percent")
        if raw is None:
            return None
        try:
            pct = float(raw)
        except (TypeError, ValueError):
            return None
        return pct if pct > 0.0 else None

    def _save_zoom_percent(self) -> None:
        if self._closed or not self._clip_ready() or self._view.width_px < 1.0:
            return
        pct = round(self._zoom_percent(), 2)
        carb.settings.get_settings().set(_ZOOM_PERCENT_SETTING, float(pct))

    def _restore_saved_zoom(self) -> None:
        if self._closed or not self._clip_ready() or self._view.width_px < 1.0:
            return
        pct = self._read_saved_zoom_percent()
        if pct is None:
            return
        lo = self._view.min_zoom_percent()
        pct = max(lo, min(100.0, pct))
        anchor = self._view.anchor_frame(self._sequence_playhead())
        self._view.set_zoom_percent(pct, anchor)
        self._grid_sig = None
        self._vp_sig = None

    def _arrow_current_source(self) -> int:
        if self._sequence is not None:
            src = self._sequence.preview_source()
            if src is not None:
                return src
        return int(self._session.last_request)

    def _seek_sequence(
        self,
        seq_frame: int,
        *,
        scrub_begin: bool = False,
        scrub_change: bool = False,
        scrub_end: bool = False,
    ) -> None:
        if self._sequence is None:
            self._session.seek_to_frame(seq_frame)
            self._refresh_playhead()
            return
        seq_frame = max(0, min(self._sequence.sequence_frame_max, int(seq_frame)))
        self._sequence.playhead = seq_frame
        src = self._sequence.preview_source(seq_frame)
        if src is None:
            self._session.set_preview_gap(True)
            if scrub_end and self._session.active:
                self._session.engine.set_scrubbing(False)
                self._session.engine.set_playback(False)
            elif scrub_begin:
                self._session.on_slider_begin()
            self._refresh_playhead()
            return
        self._session.set_preview_gap(False)
        if scrub_begin:
            self._session.on_slider_begin()
        if scrub_end:
            self._session.on_slider_end(src)
        elif scrub_change or scrub_begin:
            self._session.on_slider_change(src)
        else:
            self._session.seek_to_frame(src)
        self._refresh_playhead()

    def _on_strip_width(self) -> None:
        if (
            self._closed
            or self._strip_frame is None
            or self._clip_drag is not None
            or self._layout_refresh_depth > 0
        ):
            return
        w = float(self._strip_frame.computed_content_width)
        if w >= 1.0:
            if self._view.width_px >= 1.0 and abs(w - self._view.width_px) < _STRIP_WIDTH_EPS:
                return
            self._sync_fps()
            self._view.set_width_px(w)
            self._refresh_viewport()

    def _sync_fps(self) -> None:
        fps = 30.0
        try:
            fps = float(self._session.playback_fps())
        except Exception:
            fps = 30.0
        self._view.set_fps(fps)

    def _refresh_viewport(self) -> None:
        if (
            self._closed
            or self._pan_lead is None
            or self._pan_thumb is None
            or self._pan_tail is None
            or self._view.width_px < 1.0
            or not self._clip_ready()
        ):
            return
        ow = self._view.width_px
        left, width = self._view.overview_viewport(ow)
        lead = max(0.0, min(1.0, left / ow))
        span = max(0.002, min(1.0 - lead, width / ow))
        tail = max(0.0, 1.0 - lead - span)
        sig = (round(lead, 4), round(span, 4), round(tail, 4))
        if sig == self._vp_sig:
            return
        self._vp_sig = sig
        self._layout_refresh_depth += 1
        try:
            self._pan_lead.width = ui.Fraction(lead)
            self._pan_thumb.width = ui.Fraction(span)
            self._pan_tail.width = ui.Fraction(tail)
            self._refresh_lens()
            self._refresh_grid()
            self._refresh_clips()
            self._refresh_playhead()
        finally:
            self._layout_refresh_depth -= 1

    def _refresh_lens(self) -> None:
        if self._closed or not self._lens_bodies or self._view.width_px < 1.0 or not self._clip_ready():
            return
        ow = self._view.width_px
        left, width = self._view.overview_viewport(ow)
        right = left + width
        rows = len(self._lens_bodies)
        edge = 1.0 / ow
        for i, body in enumerate(self._lens_bodies):
            t = 0.0 if rows <= 1 else i / (rows - 1)
            row_l = left * (1.0 - t)
            row_r = right * (1.0 - t) + ow * t
            lead = max(0.0, min(1.0, row_l / ow))
            span = max(0.001, min(1.0 - lead, (row_r - row_l) / ow))
            tail = max(0.0, 1.0 - lead - span)
            self._lens_leads[i].width = ui.Fraction(lead)
            body.width = ui.Fraction(span)
            self._lens_tails[i].width = ui.Fraction(tail)
        self._sync_lens_lines(left, right, ow)

    def _mount_lens_lines(self) -> None:
        try:
            from omni.ui import color as cl
            from omni.ui_scene import scene as sc

            proj = [
                1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, -0.5, 0.0,
                0.0, 0.0, 0.0, 1.0,
            ]
            view = [
                1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0,
            ]
            scene_view = sc.SceneView(
                sc.CameraModel(proj, view),
                aspect_ratio_policy=sc.AspectRatioPolicy.STRETCH,
                width=ui.Fraction(1),
                height=ui.Fraction(1),
            )
            with scene_view.scene:
                white = cl(1.0, 1.0, 1.0, 1.0)
                self._lens_line_l = sc.Line([-1, 1, 0], [-1, -1, 0], color=white, thickness=1.25)
                self._lens_line_r = sc.Line([1, 1, 0], [1, -1, 0], color=white, thickness=1.25)
        except Exception as exc:  # noqa: BLE001
            self._lens_line_l = None
            self._lens_line_r = None
            carb.log_error(f"[v1d.tl] lens lines: {exc}")

    def _sync_lens_lines(self, left: float, right: float, ow: float) -> None:
        if self._lens_line_l is None or self._lens_line_r is None or ow < 1.0:
            return

        def pt(x_px: float, y_px: float) -> list[float]:
            return [-1.0 + 2.0 * x_px / ow, 1.0 - 2.0 * y_px / float(LENS_H), 0.0]

        self._lens_line_l.start = pt(left, 0.0)
        self._lens_line_l.end = pt(0.0, float(LENS_H))
        self._lens_line_r.start = pt(right, 0.0)
        self._lens_line_r.end = pt(ow, float(LENS_H))

    def _layout_detail_grid_row(
        self,
        track_idx: int,
        shown: list[tuple[int, int, int, int]],
        pitch: int,
        lead_px: float,
        ow: float,
    ) -> None:
        if track_idx >= len(self._cell_gaps) or track_idx >= len(self._cell_bodies):
            return
        gaps = self._cell_gaps[track_idx]
        bodies = self._cell_bodies[track_idx]
        for i in range(_CELL_POOL):
            gap = gaps[i]
            body = bodies[i]
            if i >= len(shown) or pitch < 2:
                if track_idx == 0:
                    self._cell_fracs.append(0.0)
                gap.visible = False
                body.visible = False
                gap.width = ui.Pixel(0)
                body.width = ui.Pixel(0)
                gap.style = _GAP_STYLE
                continue
            if track_idx == 0:
                self._cell_fracs.append(float(shown[i][2]) / ow)
            gap.visible = True
            body.visible = True
            gap.width = ui.Pixel(1)
            body.width = ui.Pixel(max(1, int(pitch) - 1))
            gap.style = _GAP_STYLE
        if track_idx < len(self._grid_leads) and self._grid_leads[track_idx] is not None:
            self._grid_leads[track_idx].width = ui.Pixel(max(0, int(round(lead_px))))
        if track_idx < len(self._grid_tails) and self._grid_tails[track_idx] is not None:
            self._grid_tails[track_idx].width = ui.Fraction(1)

    def _refresh_grid(self) -> None:
        if self._closed or not self._cell_bodies or not self._clip_ready() or self._view.width_px < 1.0:
            return
        sig = (
            self._view.frame_count,
            round(self._view.origin, 3),
            round(self._view.px_per_frame, 4),
            round(self._view.width_px, 1),
        )
        if sig == self._grid_sig:
            return
        self._grid_sig = sig
        cells = self._view.detail_grid(_CELL_POOL)
        self._grid_cells = cells
        ow = max(self._view.width_px, 1.0)
        shown = [c for c in cells if c[2] >= 0]
        lead_px = float(shown[0][2]) if shown else 0.0
        pitch = shown[0][3] if shown else 0
        self._cell_fracs = []
        for track_idx in range(len(self._cell_bodies)):
            self._layout_detail_grid_row(track_idx, shown, pitch, lead_px, ow)
        self._refresh_ruler(shown, ow)
        self._snap_playhead_to_gap(self._sequence_playhead())

    def _ruler_marks(self, ow: float) -> list[tuple[int, int]]:
        placed: list[tuple[int, int]] = []
        for frame in self._view.visible_ticks():
            x = int(round(self._view.x_at_frame(frame)))
            if x < 0 or x > ow:
                continue
            placed.append((frame, x))
            if len(placed) >= _RULER_TICKS:
                break
        return placed

    def _build_ruler(self) -> None:
        """Place each frame number at its frame x. Rebuilt so zoom cannot leave stale gaps."""
        ow = self._view.width_px
        if ow < 1.0 or not self._clip_ready():
            return
        with ui.ZStack(height=ui.Pixel(RULER_H)):
            for frame, x in self._ruler_marks(ow):
                with ui.Placer(
                    offset_x=ui.Pixel(x),
                    width=ui.Fraction(1),
                    height=ui.Pixel(RULER_H),
                    stable_size=True,
                    draggable=False,
                ):
                    ui.Label(
                        str(frame),
                        alignment=ui.Alignment.LEFT_CENTER,
                        style={"font_size": 12, "color": 0xFFE6E6E6},
                    )

    def _refresh_ruler(self, _cells: list[tuple[int, int, int, int]], ow: float) -> None:
        if self._ruler_frame is None or ow < 1.0:
            return
        self._ruler_frame.rebuild()

    def _hide_clip_slot(self, slot: dict[str, object]) -> None:
        lead = slot["lead"]
        body = slot["body"]
        tail = slot["tail"]
        lead.width = ui.Pixel(0)
        body.visible = False
        body.width = ui.Pixel(0)
        tail.width = ui.Fraction(1)
        label = slot.get("label")
        if label is not None:
            label.text = ""
        for key in ("edge_l", "edge_r"):
            edge = slot.get(key)
            if edge is not None:
                edge.visible = False

    def _layout_clip_in_slot(
        self,
        slot: dict[str, object],
        clip: Clip,
        track_idx: int,
        track,
        ow: float,
        *,
        dim_clip_id: str | None = None,
    ) -> None:
        lead = slot["lead"]
        body = slot["body"]
        tail = slot["tail"]
        label = slot["label"]
        label_lead = slot["label_lead"]
        edge_lead = slot["edge_lead"]
        edge_l = slot["edge_l"]
        edge_gap = slot["edge_gap"]
        edge_r = slot["edge_r"]
        block_x, block_w = self._view.clip_rect_px(clip.start_frame, clip.end_frame)
        ow_i = max(1, int(round(ow)))
        vis_l = max(0, min(ow_i, block_x))
        vis_r = max(vis_l, min(ow_i, block_x + block_w))
        vis_w = vis_r - vis_l
        lead.width = ui.Pixel(vis_l)
        body.visible = vis_w >= 1
        body.width = ui.Pixel(max(vis_w, 0))
        tail.width = ui.Fraction(1)
        label_lead.width = ui.Pixel(vis_l)
        missing_media = not Path(clip.media_path).is_file()
        if vis_w >= 1:
            name = Path(clip.media_path).name
            if missing_media:
                name = f"missing: {name}"
            elif abs(clip.speed - 1.0) > 0.01:
                name = f"{name}  ×{clip.speed:.2f}"
            label.text = name
        else:
            label.text = ""
        label.width = ui.Pixel(max(vis_w, 0))
        edge = clip_trim_edge_px(block_w, _CLIP_TRIM_PX)
        right = block_x + block_w
        left_on = vis_w >= 1 and 0 <= block_x <= ow_i
        right_on = vis_w >= 1 and 0 <= right <= ow_i
        left_w = edge if left_on else 0
        right_w = edge if right_on else 0
        if left_w + right_w > vis_w and vis_w > 0:
            left_w = vis_w // 2
            right_w = vis_w - left_w
        edge_lead.width = ui.Pixel(vis_l)
        edge_l.visible = left_w > 0
        edge_l.width = ui.Pixel(left_w)
        edge_gap.width = ui.Pixel(max(0, vis_w - left_w - right_w))
        edge_r.visible = right_w > 0
        edge_r.width = ui.Pixel(right_w)
        if dim_clip_id is not None and clip.id == dim_clip_id:
            body.style = _CLIP_DRAG_SOURCE_STYLE
        elif missing_media:
            body.style = _CLIP_MISSING_STYLE
        else:
            body.style = self._clip_style(track_idx, track)

    def _refresh_clips(self) -> None:
        if self._closed or self._sequence is None or not self._clip_ready() or self._view.width_px < 1.0:
            return
        ow = max(self._view.width_px, 1.0)
        dim_id: str | None = None
        if self._clip_drag is not None and self._clip_drag[0] == "move":
            ti_src, clip_id = self._clip_drag[1], self._clip_drag[2]
            if self._move_drag_dest is not None and self._move_drag_dest != ti_src:
                dim_id = clip_id
        for ti, track in enumerate(self._sequence.tracks):
            if ti >= len(self._clip_slots):
                break
            slots = self._clip_slots[ti]
            clips = sorted(track.clips, key=lambda c: c.start_frame)
            for si, slot in enumerate(slots):
                if si < len(clips):
                    self._layout_clip_in_slot(
                        slot,
                        clips[si],
                        ti,
                        track,
                        ow,
                        dim_clip_id=dim_id,
                    )
                else:
                    self._hide_clip_slot(slot)

    def _clip_style(self, track_index: int, track) -> dict:
        if not getattr(track, "video_enabled", True):
            return _CLIP_OFF_STYLE
        if self._sequence is not None and track_index == self._sequence.selected_track:
            return _CLIP_SELECTED_STYLE
        return _CLIP_STYLE

    def _icon_url(self, name: str) -> str:
        return str(_ICON_DIR / f"{name}.svg")

    def _header_button(self, name: str, tip: str, clicked, track_idx: int) -> ui.Button:
        return ui.Button(
            "",
            width=28,
            height=28,
            image_url=self._icon_url(name),
            image_width=14,
            image_height=14,
            tooltip=tip,
            clicked_fn=clicked,
            mouse_pressed_fn=lambda x, y, b, m, ti=track_idx: self._on_track_header_pressed(ti, b, y),
        )

    def _on_track_header_pressed(self, track_idx: int, button: int, local_y: float) -> None:
        if button != _MOUSE_RIGHT:
            return
        if not self._clip_ready() or self._sequence is None:
            return
        self._show_track_menu(track_idx, local_y)

    def _load_track_count(self) -> int:
        raw = carb.settings.get_settings().get(_TRACK_COUNT_SETTING)
        try:
            n = int(raw)
        except (TypeError, ValueError):
            n = DEFAULT_TRACK_ROWS
        return max(1, min(MAX_TRACKS, n))

    def _store_track_count(self) -> None:
        if self._sequence is None:
            return
        carb.settings.get_settings().set(_TRACK_COUNT_SETTING, len(self._sequence.tracks))

    def _ui_row_count(self) -> int:
        if self._sequence is not None:
            return len(self._sequence.tracks)
        return self._load_track_count()

    def _reset_track_widget_lists(self) -> None:
        self._cell_gaps = []
        self._cell_bodies = []
        self._grid_leads = []
        self._grid_tails = []
        self._clip_slots = []
        self._track_drop_hilite = []
        self._track_ghost_leads = []
        self._track_ghost_bodies = []
        self._track_clip_leads = []
        self._track_clip_tails = []
        self._track_clip_bodies = []
        self._track_clip_labels = []
        self._track_clip_label_leads = []
        self._track_clip_edge_leads = []
        self._track_clip_edge_gaps = []
        self._track_clip_edge_l = []
        self._track_clip_edge_r = []

    def _rebuild_rows(self) -> None:
        if self._clip_drag is not None or self._header_drag is not None:
            return
        n = self._ui_row_count()
        h_strip = _detail_strip_h(n)
        h_time = _time_pane_h(n)
        if self._detail_strip_zstack is not None:
            self._detail_strip_zstack.height = ui.Pixel(h_strip)
        if self._detail_play_frame is not None:
            self._detail_play_frame.height = ui.Pixel(h_strip)
        if self._time_pane_hstack is not None:
            self._time_pane_hstack.height = ui.Pixel(h_time)
        if self._strip_frame is not None:
            self._strip_frame.height = ui.Pixel(h_time)
        if self._track_header_frame is not None:
            self._track_header_frame.height = ui.Pixel(h_strip)
        if self._track_rows_frame is not None:
            self._track_rows_frame.rebuild()
        if self._track_header_frame is not None:
            self._track_header_frame.rebuild()
        self._grid_sig = None
        self._vp_sig = None
        self._refresh_track_headers()
        self._refresh_clips()
        self._refresh_grid()
        self._refresh_playhead()

    def _build_track_rows(self) -> None:
        self._reset_track_widget_lists()
        track_count = self._ui_row_count()
        with ui.VStack(spacing=0):
            for track_idx in range(track_count):
                with ui.ZStack(height=ui.Pixel(DETAIL_H)):
                    ui.Rectangle(
                        height=ui.Pixel(DETAIL_H),
                        style={"background_color": 0xFFFFFFFF},
                        opaque_for_mouse_events=False,
                    )
                    track_gaps: list[ui.Rectangle] = []
                    track_bodies: list[ui.Rectangle] = []
                    with ui.HStack(spacing=0, height=ui.Pixel(DETAIL_H)):
                        grid_lead = ui.Spacer(width=ui.Fraction(0))
                        for _ in range(_CELL_POOL):
                            gap = ui.Rectangle(
                                width=ui.Pixel(0),
                                height=ui.Pixel(DETAIL_H),
                                style=_GAP_STYLE,
                                opaque_for_mouse_events=False,
                            )
                            body = ui.Rectangle(
                                width=ui.Pixel(0),
                                height=ui.Pixel(DETAIL_H),
                                style=_FRAME_STYLE,
                                opaque_for_mouse_events=False,
                            )
                            track_gaps.append(gap)
                            track_bodies.append(body)
                        grid_tail = ui.Spacer(width=ui.Fraction(1))
                    self._grid_leads.append(grid_lead)
                    self._grid_tails.append(grid_tail)
                    self._cell_gaps.append(track_gaps)
                    self._cell_bodies.append(track_bodies)
                    drop_hi = ui.Rectangle(
                        width=ui.Fraction(1),
                        height=ui.Pixel(DETAIL_H),
                        style=_TRACK_DROP_STYLE,
                        visible=False,
                        opaque_for_mouse_events=False,
                    )
                    self._track_drop_hilite.append(drop_hi)
                    with ui.HStack(spacing=0, height=ui.Pixel(DETAIL_H)):
                        ghost_lead = ui.Rectangle(
                            width=ui.Pixel(0),
                            height=ui.Pixel(DETAIL_H),
                            style=_CLEAR,
                            visible=False,
                            opaque_for_mouse_events=False,
                        )
                        ghost_body = ui.Rectangle(
                            width=ui.Pixel(1),
                            height=ui.Pixel(DETAIL_H),
                            style=_GHOST_OK_STYLE,
                            visible=False,
                            opaque_for_mouse_events=False,
                        )
                        ui.Spacer(width=ui.Fraction(1))
                    self._track_ghost_leads.append(ghost_lead)
                    self._track_ghost_bodies.append(ghost_body)
                    track_slots: list[dict[str, object]] = []
                    for _slot in range(_CLIP_POOL_PER_ROW):
                        with ui.HStack(spacing=0, height=ui.Pixel(DETAIL_H)):
                            clip_lead = ui.Rectangle(
                                width=ui.Pixel(0),
                                height=ui.Pixel(DETAIL_H),
                                style=_CLEAR,
                                opaque_for_mouse_events=False,
                            )
                            clip_body = ui.Rectangle(
                                width=ui.Pixel(1),
                                height=ui.Pixel(DETAIL_H),
                                style=_CLIP_STYLE,
                                opaque_for_mouse_events=False,
                            )
                            clip_tail = ui.Spacer(width=ui.Fraction(1))
                        with ui.HStack(spacing=0, height=ui.Pixel(DETAIL_H)):
                            label_lead = ui.Rectangle(
                                width=ui.Pixel(0),
                                height=ui.Pixel(DETAIL_H),
                                style=_CLEAR,
                                opaque_for_mouse_events=False,
                            )
                            clip_label = ui.Label(
                                "",
                                width=ui.Pixel(1),
                                alignment=ui.Alignment.CENTER,
                                style={"font_size": 11, "color": 0xFFE8E8E8},
                            )
                            ui.Spacer(width=ui.Fraction(1))
                        with ui.HStack(spacing=0, height=ui.Pixel(DETAIL_H)):
                            edge_lead = ui.Rectangle(
                                width=ui.Pixel(0),
                                height=ui.Pixel(DETAIL_H),
                                style=_CLEAR,
                                opaque_for_mouse_events=False,
                            )
                            clip_edge_l = ui.Rectangle(
                                width=ui.Pixel(_CLIP_TRIM_PX),
                                height=ui.Pixel(DETAIL_H),
                                style=_CLIP_EDGE_STYLE,
                                opaque_for_mouse_events=False,
                            )
                            edge_gap = ui.Rectangle(
                                width=ui.Pixel(1),
                                height=ui.Pixel(DETAIL_H),
                                style=_CLEAR,
                                opaque_for_mouse_events=False,
                            )
                            clip_edge_r = ui.Rectangle(
                                width=ui.Pixel(_CLIP_TRIM_PX),
                                height=ui.Pixel(DETAIL_H),
                                style=_CLIP_EDGE_STYLE,
                                opaque_for_mouse_events=False,
                            )
                            ui.Spacer(width=ui.Fraction(1))
                        track_slots.append(
                            {
                                "lead": clip_lead,
                                "body": clip_body,
                                "tail": clip_tail,
                                "label_lead": label_lead,
                                "label": clip_label,
                                "edge_lead": edge_lead,
                                "edge_l": clip_edge_l,
                                "edge_gap": edge_gap,
                                "edge_r": clip_edge_r,
                            }
                        )
                    self._clip_slots.append(track_slots)
                    if track_slots:
                        s0 = track_slots[0]
                        self._track_clip_leads.append(s0["lead"])
                        self._track_clip_bodies.append(s0["body"])
                        self._track_clip_tails.append(s0["tail"])
                        self._track_clip_label_leads.append(s0["label_lead"])
                        self._track_clip_labels.append(s0["label"])
                        self._track_clip_edge_leads.append(s0["edge_lead"])
                        self._track_clip_edge_l.append(s0["edge_l"])
                        self._track_clip_edge_gaps.append(s0["edge_gap"])
                        self._track_clip_edge_r.append(s0["edge_r"])
                    ui.Rectangle(
                        width=ui.Fraction(1),
                        height=ui.Pixel(DETAIL_H),
                        style={"background_color": 0x01000000},
                        opaque_for_mouse_events=True,
                        mouse_pressed_fn=lambda x, y, b, m, ti=track_idx: self._on_track_pressed(ti, x, y, b, m),
                        mouse_moved_fn=lambda x, y, *_rest, ti=track_idx: self._on_track_moved(ti, x, y, 0, 0),
                        mouse_released_fn=lambda x, y, b, m, ti=track_idx: self._on_track_released(ti, x, y, b, m),
                    )
                if track_idx < track_count - 1:
                    ui.Rectangle(
                        width=ui.Fraction(1),
                        height=ui.Pixel(_TRACK_DIVIDER_H),
                        style=_TRACK_DIVIDER_STYLE,
                        opaque_for_mouse_events=False,
                    )

    def _build_track_header_rows(self) -> None:
        self._track_titles = []
        self._track_eyes = []
        self._track_speakers = []
        track_count = self._ui_row_count()
        with ui.VStack(spacing=0):
            for track_idx in range(track_count):
                with ui.HStack(width=ui.Pixel(COLUMN_W), height=ui.Pixel(DETAIL_H), spacing=4):
                    with ui.ZStack(width=36, height=ui.Pixel(DETAIL_H)):
                        title = ui.Label(
                            f"T{track_idx + 1}",
                            alignment=ui.Alignment.CENTER,
                            style=_COLUMN_LABEL,
                        )
                        ui.Rectangle(
                            width=36,
                            height=ui.Pixel(DETAIL_H),
                            style={"background_color": 0x01000000},
                            opaque_for_mouse_events=True,
                            mouse_pressed_fn=lambda x, y, b, m, ti=track_idx: self._on_title_pressed(ti, y, b),
                            mouse_moved_fn=lambda x, y, m, b, ti=track_idx: self._on_title_moved(ti, y),
                            mouse_released_fn=lambda x, y, b, m, ti=track_idx: self._on_title_released(ti, y, b),
                        )
                    eye = self._header_button(
                        "eye",
                        "Video on",
                        lambda ti=track_idx: self._on_eye_clicked(ti),
                        track_idx,
                    )
                    speaker = self._header_button(
                        "speaker",
                        "Audio on",
                        lambda ti=track_idx: self._on_speaker_clicked(ti),
                        track_idx,
                    )
                    ui.Rectangle(
                        width=ui.Fraction(1),
                        height=ui.Pixel(DETAIL_H),
                        style={"background_color": 0x01000000},
                        opaque_for_mouse_events=True,
                        mouse_pressed_fn=lambda x, y, b, m, ti=track_idx: self._on_title_pressed(ti, y, b),
                    )
                self._track_titles.append(title)
                self._track_eyes.append(eye)
                self._track_speakers.append(speaker)
                if track_idx < track_count - 1:
                    ui.Rectangle(
                        height=ui.Pixel(_TRACK_DIVIDER_H),
                        style=_TRACK_DIVIDER_STYLE,
                        opaque_for_mouse_events=False,
                    )

    def _row_local_y_from_strip(self, track_idx: int) -> float | None:
        pos = self._pointer_over_strip()
        if pos is None:
            return None
        _x, y = pos
        rel = float(y) - float(LENS_H + RULER_H)
        if rel < 0.0:
            return None
        stride = float(DETAIL_H + _TRACK_DIVIDER_H)
        local = rel - float(track_idx) * stride
        if 0.0 <= local < float(DETAIL_H):
            return local
        return None

    def _row_local_y_from_header(self, track_idx: int) -> float | None:
        frame = self._track_header_frame
        if frame is None:
            return None
        iinput = carb.input.acquire_input_interface()
        mouse = omni.appwindow.get_default_app_window().get_mouse()
        pos = iinput.get_mouse_coords_pixel(mouse)
        py = float(pos[1]) - float(frame.screen_position_y)
        stride = float(DETAIL_H + _TRACK_DIVIDER_H)
        local = py - float(track_idx) * stride
        if 0.0 <= local < float(DETAIL_H):
            return local
        return None

    def _row_local_y_for_menu(self, track_idx: int, event_y: float | None) -> float:
        """Row-local y (0..DETAIL_H) for above/below insert. Event y is often strip/stack coords."""
        from_header = self._row_local_y_from_header(track_idx)
        if from_header is not None:
            return from_header
        from_strip = self._row_local_y_from_strip(track_idx)
        if from_strip is not None:
            return from_strip
        if event_y is None:
            return float(DETAIL_H) * 0.75
        y = float(event_y)
        if y >= float(DETAIL_H):
            rel = y - float(LENS_H + RULER_H)
            stride = float(DETAIL_H + _TRACK_DIVIDER_H)
            local = rel - float(track_idx) * stride
            if 0.0 <= local < float(DETAIL_H):
                return local
        # Eye/speaker buttons report y inside the 28px icon, not the 64px row.
        if y <= 28.0:
            y = (float(DETAIL_H) - 28.0) * 0.5 + y
        return y

    def _show_track_menu(self, track_idx: int, local_y: float | None = None) -> None:
        if self._closed or self._sequence is None:
            return
        if self._session.play_dir != 0:
            self._session.transport_stop()
        self._track_menu_track = track_idx
        y = self._row_local_y_for_menu(track_idx, local_y)
        self._track_menu_insert_above = y < float(DETAIL_H) * 0.5
        n = len(self._sequence.tracks)
        if self._track_menu is not None:
            try:
                self._track_menu.hide()
            except Exception:
                pass
        self._track_menu = ui.Menu("v1d.tl.track")
        with self._track_menu:
            ui.MenuItem(
                "Add Track",
                triggered_fn=self._on_add_track_menu,
                enabled=n < MAX_TRACKS,
            )
            ui.MenuItem(
                "Delete Track",
                triggered_fn=self._on_delete_track_menu,
                enabled=n > 1,
            )
        self._track_menu.show()

    def _on_add_track_menu(self) -> None:
        if self._closed or self._sequence is None:
            return
        track = self._sequence.add_track(
            self._track_menu_track,
            above=self._track_menu_insert_above,
        )
        if track is None:
            return
        self._store_track_count()
        self._rebuild_rows()
        self._commit_preview()
        self._sync_cursor()
        if self._status is not None:
            self._status.text = f"Added T{track.index + 1}"

    def _on_delete_track_menu(self) -> None:
        if self._closed or self._sequence is None:
            return
        ti = self._track_menu_track
        if not self._sequence.delete_track(ti):
            return
        self._store_track_count()
        self._rebuild_rows()
        self._commit_preview()
        self._sync_cursor()
        if self._status is not None:
            self._status.text = f"Deleted T{ti + 1}"

    def _build_track_column(self) -> None:
        with ui.VStack(width=ui.Pixel(COLUMN_W), spacing=0):
            with ui.ZStack(width=ui.Pixel(COLUMN_W), height=ui.Pixel(LENS_H)):
                ui.Rectangle(
                    width=ui.Pixel(COLUMN_W),
                    height=ui.Pixel(LENS_H),
                    style=_COLUMN_BG,
                )
                ui.Label(
                    "Lens",
                    alignment=ui.Alignment.CENTER,
                    style=_COLUMN_LABEL,
                )
            with ui.ZStack(width=ui.Pixel(COLUMN_W), height=ui.Pixel(RULER_H)):
                ui.Rectangle(
                    width=ui.Pixel(COLUMN_W),
                    height=ui.Pixel(RULER_H),
                    style=_COLUMN_BG,
                )
                ui.Label(
                    "Frames",
                    alignment=ui.Alignment.CENTER,
                    style=_COLUMN_LABEL,
                )
            self._track_header_frame = ui.Frame(
                width=ui.Pixel(COLUMN_W),
                height=ui.Pixel(_detail_strip_h(self._ui_row_count())),
                build_fn=self._build_track_header_rows,
            )

    def _refresh_track_headers(self) -> None:
        if self._sequence is None:
            return
        for i, track in enumerate(self._sequence.tracks):
            if i >= len(self._track_titles):
                break
            self._track_titles[i].text = f"T{i + 1}"
            video_on = bool(getattr(track, "video_enabled", True))
            audio_on = bool(getattr(track, "audio_enabled", True))
            self._track_eyes[i].image_url = self._icon_url("eye" if video_on else "eye-off")
            self._track_eyes[i].tooltip = "Video on" if video_on else "Video off"
            self._track_speakers[i].image_url = self._icon_url("speaker" if audio_on else "speaker-off")
            self._track_speakers[i].tooltip = "Audio on" if audio_on else "Audio off"

    def _row_at_local_y(self, index: int, y: float) -> int:
        if self._sequence is None:
            return index
        n = len(self._sequence.tracks)
        if y >= float(DETAIL_H) and index + 1 < n:
            return index + 1
        if y < 0.0 and index > 0:
            return index - 1
        return index

    def _drop_track_index(self, origin: int) -> int:
        """Row under the pointer, in strip coordinates. Release y is not row-local."""
        pos = self._pointer_over_strip()
        if pos is None:
            return origin
        dest = self._track_index_at_strip_y(pos[1])
        if dest is None:
            return origin
        return dest

    def _configure_timeline_for_session(self) -> None:
        if self._sequence is None:
            self._session.clear_timeline()
            return
        span = self._sequence.sequence_playback_span()
        if span is None:
            self._session.clear_timeline()
            return
        lo, hi = span
        self._session.configure_timeline(
            lo,
            hi,
            lambda s: self._sequence.preview_source(s),
            media_at_sequence=self._preview_media_at,
        )

    def _preview_media_at(self, seq: int) -> str | None:
        if self._sequence is None:
            return None
        clip = self._sequence.preview_clip(seq)
        if clip is None:
            return None
        return clip.media_path

    def _sync_dirty_title(self) -> None:
        star = " *" if self._project_is_dirty() else ""
        doc = Path(self._project_path).name if self._project_path else ""
        doc_title = f"{doc}{star}" if doc else (star.strip() or "")
        try:
            from omni.kit.window.title import get_main_window_title

            wt = get_main_window_title()
            if wt is not None:
                wt.set_title(doc_title)
                return
        except ImportError:
            pass
        base = getattr(self, "_window_title", WINDOW_TITLE)
        self._window.title = f"{base}{star}"

    def _commit_preview(self) -> None:
        if self._sequence is None:
            return
        self._configure_timeline_for_session()
        clip = self._sequence.preview_clip()
        if clip is not None:
            self._session.ensure_media_path(clip.media_path)
        src = self._sequence.preview_source()
        if src is None:
            self._session.set_preview_gap(True)
            self._refresh_playhead()
            self._sync_dirty_title()
            return
        was_gap = self._session.preview_gap
        self._session.set_preview_gap(False)
        if was_gap or int(src) != int(self._session.last_request):
            self._session.seek_to_frame(int(src))
        self._refresh_playhead()
        self._sync_dirty_title()

    def _start_transport(self, direction: int) -> None:
        session = self._session
        if self._sequence is not None:
            self._configure_timeline_for_session()
            ph = self._sequence_playhead()
            src = self._sequence.preview_source(ph)
            if src is not None:
                session.set_preview_gap(False)
                if int(src) != int(session.last_request):
                    session.on_slider_begin()
                    session.on_slider_change(int(src))
                    session.on_slider_end(int(src))
            else:
                session._preview_gap = True
            session.transport_play(direction, origin_sequence=ph)
        else:
            session.set_preview_gap(False)
            session.transport_play(direction)

    def _on_eye_clicked(self, index: int) -> None:
        if self._sequence is None or index >= len(self._sequence.tracks):
            return
        track = self._sequence.tracks[index]
        track.video_enabled = not bool(getattr(track, "video_enabled", True))
        self._refresh_track_headers()
        self._refresh_clips()
        self._commit_preview()

    def _on_speaker_clicked(self, index: int) -> None:
        if self._sequence is None or index >= len(self._sequence.tracks):
            return
        track = self._sequence.tracks[index]
        track.audio_enabled = not bool(getattr(track, "audio_enabled", True))
        self._refresh_track_headers()

    def _on_title_pressed(self, index: int, y: float, button: int) -> None:
        if self._sequence is None:
            return
        if button == _MOUSE_RIGHT:
            if self._clip_ready():
                self._show_track_menu(index, y)
            return
        if button != _MOUSE_LEFT:
            return
        self._header_drag = (index, float(y))
        self._sequence.selected_track = index
        self._refresh_clips()

    def _on_title_moved(self, index: int, y: float) -> None:
        if self._header_drag is None or self._header_drag[0] != index:
            return

    def _on_title_released(self, index: int, y: float, button: int) -> None:
        if button != _MOUSE_LEFT or self._header_drag is None or self._sequence is None:
            return
        origin, _y0 = self._header_drag
        self._header_drag = None
        if origin != index:
            return
        dest = self._row_at_local_y(origin, y)
        if dest != origin:
            self._sequence.move_track(origin, dest)
        self._refresh_track_headers()
        self._refresh_clips()
        self._commit_preview()

    def _refresh_playhead(self) -> None:
        if self._closed or not self._clip_ready() or self._view.width_px < 1.0:
            return
        frame = self._sequence_playhead()
        if self._clock is not None:
            self._clock.text = self._timecode(frame)
        self._snap_playhead_to_gap(frame)
        self._place_detail_playhead(frame)
        if self._full_play_lead is not None and self._full_play_tail is not None:
            total = max(self._timeline_frame_count(), 1)
            rel = int(frame) / total
            rel = max(0.0, min(1.0, rel))
            self._full_play_lead.width = ui.Fraction(rel)
            self._full_play_tail.width = ui.Fraction(1.0 - rel)
        self._sync_scissor_enabled()

    def _snap_playhead_to_gap(self, frame: int) -> None:
        """Magenta line is the white gap that starts the frame shown in the preview."""
        for track_gaps in self._cell_gaps:
            for i, (start, n, _x, _pitch) in enumerate(self._grid_cells):
                if i >= len(track_gaps):
                    break
                on = start <= frame < start + n
                track_gaps[i].style = _PLAYHEAD_STYLE if on else _GAP_STYLE

    def _playhead_tip_x(self, frame: int) -> int | None:
        """Left edge of the 1 px line. The triangle point uses the same x."""
        if self._view.width_px < 1.0:
            return None
        x = int(round(self._view.x_at_frame(int(frame))))
        ow = int(round(self._view.width_px))
        if x < 0 or x > ow:
            return None
        return x

    def _place_detail_playhead(self, frame: int) -> None:
        """Draw the V and the track line on the same pixel as that frame's ruler tick."""
        x = self._playhead_tip_x(frame)
        if x == self._playhead_mark_x:
            return
        self._playhead_mark_x = x
        if self._play_head_frame is not None:
            self._play_head_frame.rebuild()
        if self._detail_play_frame is not None:
            self._detail_play_frame.rebuild()

    def _build_play_head(self) -> None:
        x = self._playhead_mark_x
        if x is None:
            return
        left = int(round(float(x) - (_PLAYHEAD_TRI_W / 2.0)))
        with ui.Placer(
            offset_x=ui.Pixel(left),
            offset_y=ui.Pixel(RULER_H - _PLAYHEAD_TRI_H),
            width=ui.Pixel(_PLAYHEAD_TRI_W),
            height=ui.Pixel(_PLAYHEAD_TRI_H),
            stable_size=True,
            draggable=False,
        ):
            ui.Triangle(
                width=ui.Pixel(_PLAYHEAD_TRI_W),
                height=ui.Pixel(_PLAYHEAD_TRI_H),
                alignment=ui.Alignment.CENTER_BOTTOM,
                style=_PLAYHEAD_STYLE,
                opaque_for_mouse_events=True,
                mouse_pressed_fn=self._on_playhead_pressed,
                mouse_moved_fn=self._on_playhead_moved,
                mouse_released_fn=self._on_playhead_released,
            )

    def _build_detail_playhead(self) -> None:
        x = self._playhead_mark_x
        if x is None:
            return
        strip_h = _detail_strip_h(self._ui_row_count())
        with ui.Placer(
            offset_x=ui.Pixel(int(x)),
            width=ui.Pixel(1),
            height=ui.Pixel(strip_h),
            stable_size=True,
            draggable=False,
        ):
            ui.Rectangle(
                width=ui.Pixel(1),
                height=ui.Pixel(strip_h),
                style=_PLAYHEAD_STYLE,
                opaque_for_mouse_events=False,
            )

    def _strip_layout_x(self) -> float | None:
        """Pointer x in the same pixels as the ruler ticks."""
        pos = self._pointer_over_strip()
        if pos is None:
            return None
        x = float(pos[0])
        widget = self._strip_frame
        w = float(widget.computed_width) if widget is not None else 0.0
        ow = float(self._view.width_px)
        if w > 1.0 and ow > 1.0 and abs(w - ow) > 1.0:
            x = x / w * ow
        if ow > 1.0:
            x = max(0.0, min(ow, x))
        return x

    def _playhead_frame_under_grab(self) -> int | None:
        x = self._strip_layout_x()
        if x is None or not self._clip_ready():
            return None
        return self._view.frame_at_x(float(x) - float(self._playhead_grab_dx))

    def _on_ruler_pressed(self, x: float, _y: float, button: int, _mod: int) -> None:
        if button != _MOUSE_LEFT or not self._clip_ready() or self._sequence is None:
            return
        local = self._strip_layout_x()
        if local is None:
            local = float(x)
        frame = self._view.frame_at_x(local)
        self._seek_sequence(frame, scrub_begin=True, scrub_change=True, scrub_end=True)

    def _on_playhead_pressed(self, _x: float, _y: float, button: int, _mod: int) -> None:
        if button != _MOUSE_LEFT or not self._clip_ready() or self._sequence is None:
            return
        local = self._strip_layout_x()
        tip = self._playhead_tip_x(self._sequence_playhead())
        if local is None or tip is None:
            return
        self._playhead_drag = True
        self._playhead_grab_dx = float(local) - float(tip)
        self._seek_sequence(self._sequence_playhead(), scrub_begin=True, scrub_change=True)
        self._sync_cursor()

    def _on_playhead_moved(self, _x: float, _y: float, *_rest) -> None:
        if not self._playhead_drag:
            return
        frame = self._playhead_frame_under_grab()
        if frame is not None and frame != self._sequence_playhead():
            self._seek_sequence(frame, scrub_change=True)

    def _on_playhead_released(self, _x: float, _y: float, button: int, _mod: int) -> None:
        if button != _MOUSE_LEFT:
            return
        self._finish_playhead_drag()

    def _finish_playhead_drag(self) -> None:
        if not self._playhead_drag:
            return
        self._playhead_drag = False
        frame = self._playhead_frame_under_grab()
        if frame is None:
            frame = self._sequence_playhead()
        self._seek_sequence(frame, scrub_end=True)
        self._sync_cursor()

    def _mouse_left_down(self) -> bool:
        try:
            iinput = carb.input.acquire_input_interface()
            mouse = omni.appwindow.get_default_app_window().get_mouse()
            return float(iinput.get_mouse_value(mouse, carb.input.MouseInput.LEFT_BUTTON)) > 0.5
        except Exception:
            return False

    def _strip_pointer_local_x(self) -> float:
        """Horizontal position over the timeline strip for wheel zoom."""
        widget = self._strip_frame
        if widget is None or self._view.width_px < 1.0:
            return self._view.width_px * 0.5
        iinput = carb.input.acquire_input_interface()
        mouse = omni.appwindow.get_default_app_window().get_mouse()
        pos = iinput.get_mouse_coords_pixel(mouse)
        px = float(pos[0])
        x = px - float(widget.screen_position_x)
        w = float(widget.computed_width)
        if w < 1.0:
            return self._view.width_px * 0.5
        return max(0.0, min(w, x))

    def _pointer_local_x(self) -> float | None:
        widget = self._full_input
        if widget is None:
            return None
        iinput = carb.input.acquire_input_interface()
        mouse = omni.appwindow.get_default_app_window().get_mouse()
        pos = iinput.get_mouse_coords_pixel(mouse)
        px = float(pos[0])
        py = float(pos[1])
        x = px - float(widget.screen_position_x)
        y = py - float(widget.screen_position_y)
        w = float(widget.computed_width)
        h = float(widget.computed_height)
        if w < 1.0 or h < 1.0 or x < 0.0 or y < 0.0 or x > w or y > h:
            return None
        return x

    def _on_body_hover(self, hovered: bool) -> None:
        if not hovered and self._full_drag is None:
            self._sync_cursor()

    def _ensure_hand_cursors(self, renderer) -> None:
        if self._hand_ready:
            return
        import pathlib

        folder = pathlib.Path(__file__).resolve().parent / "cursors"
        folder.mkdir(exist_ok=True)
        written: dict[str, pathlib.Path] = {}
        for key, theme_name, fallback in (
            ("v1d-open-hand", "grab", _OPEN_HAND),
            ("v1d-grab-hand", "grabbing", _GRAB_HAND),
            ("v1d-ew", "ew-resize", _EW_ARROW),
        ):
            path = folder / f"{key}.png"
            blob = None
            src = _theme_cursor_path(theme_name)
            if src:
                blob = _xcursor_png(src, 24)
            if blob is None:
                blob = _hand_png(fallback)
            path.write_bytes(blob)
            written[key] = path
        for key, path in written.items():
            renderer.register_cursor_shape_extend(key, str(path))
        self._hand_ready = True

    def _pointer_over_strip(self) -> tuple[float, float] | None:
        widget = self._strip_frame
        if widget is None:
            return None
        iinput = carb.input.acquire_input_interface()
        mouse = omni.appwindow.get_default_app_window().get_mouse()
        pos = iinput.get_mouse_coords_pixel(mouse)
        x = float(pos[0]) - float(widget.screen_position_x)
        y = float(pos[1]) - float(widget.screen_position_y)
        w = float(widget.computed_width)
        h = float(widget.computed_height)
        if w < 1.0 or h < 1.0 or x < 0.0 or y < 0.0 or x > w or y > h:
            return None
        return x, y

    def _track_index_at_strip_y(self, y: float) -> int | None:
        rel = float(y) - float(LENS_H + RULER_H)
        if rel < 0.0:
            return None
        stride = float(DETAIL_H + _TRACK_DIVIDER_H)
        idx = int(rel // stride)
        within = rel - idx * stride
        n = self._ui_row_count()
        if idx < 0 or idx >= n or within >= float(DETAIL_H):
            return None
        return idx

    def _clip_hover_zone(self) -> str | None:
        if not self._clip_ready() or self._sequence is None:
            return None
        pos = self._pointer_over_strip()
        if pos is None:
            return None
        x, y = pos
        track_idx = self._track_index_at_strip_y(y)
        if track_idx is None:
            return None
        hit, _frame = self._clip_hit(track_idx, x)
        return hit

    def _sync_cursor(self) -> None:
        clip_kind = self._clip_drag[0] if self._clip_drag else None
        if self._playhead_drag:
            kind = "grab"
        elif clip_kind in ("trim_left", "trim_right") or self._full_drag in ("resize_left", "resize_right"):
            kind = "ew"
        elif self._full_drag == "pan":
            kind = "grab"
        else:
            zone = self._clip_hover_zone()
            if zone in ("trim_left", "trim_right"):
                kind = "ew"
            else:
                local = self._pointer_local_x()
                if local is None:
                    kind = "arrow"
                else:
                    hit, _left, _width = self._full_hit(local)
                    if hit in ("resize_left", "resize_right"):
                        kind = "ew"
                    elif hit == "body":
                        kind = "open"
                    else:
                        kind = "arrow"
        if kind == self._cursor_kind and kind == "arrow":
            return
        self._cursor_kind = kind
        try:
            import omni.kit.imgui_renderer as imgui_renderer

            app = omni.appwindow.get_default_app_window()
            renderer = imgui_renderer.get_imgui_renderer_interface()
            if kind == "ew":
                import carb.windowing

                self._ensure_hand_cursors(renderer)
                renderer.clear_cursor_shape_override(app)
                renderer.set_cursor_shape_override(
                    app, carb.windowing.CursorStandardShape.HORIZONTAL_RESIZE
                )
                renderer.set_cursor_shape_override_extend(app, "v1d-ew")
            elif kind in ("open", "grab"):
                self._ensure_hand_cursors(renderer)
                name = "v1d-grab-hand" if kind == "grab" else "v1d-open-hand"
                renderer.set_cursor_shape_override_extend(app, name)
            else:
                import carb.windowing

                renderer.clear_cursor_shape_override(app)
                renderer.set_cursor_shape_override(app, carb.windowing.CursorStandardShape.ARROW)
        except Exception as exc:  # noqa: BLE001
            carb.log_warn(f"[v1d.tl] cursor: {exc}")

    def _event_width(self) -> float:
        w = 0.0
        if self._full_input is not None:
            w = float(self._full_input.computed_width)
        if w < 1.0 and self._strip_frame is not None:
            w = float(self._strip_frame.computed_content_width)
        if w >= 1.0:
            self._view.set_width_px(w)
        return self._view.width_px

    def _full_hit(self, x: float) -> tuple[str, float, float]:
        ow = self._event_width()
        left, width = self._view.overview_viewport(ow)
        if width <= 0.5:
            return "outside", left, width
        edge = float(_EDGE_PX) if width >= 36.0 else max(4.0, width * 0.25)
        right = left + width
        if x < left - edge or x > right + edge:
            return "outside", left, width
        if x >= right - edge:
            return "resize_right", left, width
        if x <= left + edge:
            return "resize_left", left, width
        return "body", left, width

    def _on_full_pressed(self, x: float, _y: float, button: int, _mod: int) -> None:
        if not self._clip_ready() or button != _MOUSE_LEFT or self._event_width() < 1.0:
            return
        hit, left, width = self._full_hit(x)
        ow = self._view.width_px
        if hit == "outside":
            self._view.align_on_play = True
            self._view.center_on_overview_x(x, ow)
            self._refresh_viewport()
            return
        if hit == "body":
            if self._view.pan_max() <= 1e-3:
                return
            self._full_drag = "pan"
            self._view.align_on_play = True
            self._full_grab = x - left
            self._sync_cursor()
            return
        if hit == "resize_left":
            self._full_drag = "resize_left"
            self._resize_right_px = left + width
            self._resize_anchor_frame = self._view.right_edge_frame()
            return
        if hit == "resize_right":
            self._full_drag = "resize_right"
            self._resize_left_px = left

    def _on_full_moved(self, x: float, _y: float, _mod: int, _b: int) -> None:
        if self._full_drag is None or not self._clip_ready() or self._event_width() < 1.0:
            return
        ow = self._view.width_px
        fc = max(self._view.frame_count, 1)
        if self._full_drag == "pan":
            self._view.origin_from_overview_left(x - self._full_grab, ow)
            self._refresh_viewport()
            return
        if self._full_drag == "resize_right":
            span = max(1.0, x - self._resize_left_px) / ow * fc
            self._view.zoom_to_span(span, int(self._view.origin), "left")
            self._refresh_viewport()
            return
        if self._full_drag == "resize_left":
            span = max(1.0, self._resize_right_px - x) / ow * fc
            self._view.zoom_to_span(span, int(self._resize_anchor_frame), "right")
            self._refresh_viewport()

    def _frame_at_detail_x(self, x: float) -> int:
        """Frame that starts at the white gap at or left of x. That frame is on the preview."""
        cells = self._grid_cells or self._view.detail_grid(_CELL_POOL)
        if not cells:
            return self._view.frame_at_x(x)
        chosen = cells[0][0]
        for start, _n, gx, pitch in cells:
            if gx <= x < gx + pitch:
                return start
            if gx <= x:
                chosen = start
        return chosen

    def _timecode(self, frame: int) -> str:
        fps = 30.0
        try:
            fps = float(self._session.playback_fps())
        except Exception:
            fps = 30.0
        fps_i = max(1, int(round(fps)))
        frame = max(0, int(frame))
        ff = frame % fps_i
        total = frame // fps_i
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}h:{m:02d}m:{s:02d}s:{ff:02d}f"

    def _clip_hit(self, track_idx: int, x: float) -> tuple[str, int]:
        seq_frame = self._view.frame_at_x(x)
        if self._sequence is None or track_idx >= len(self._sequence.tracks):
            return "empty", seq_frame
        track = self._sequence.tracks[track_idx]
        clip = track.clip_at_sequence(seq_frame)
        if clip is None:
            return "empty", seq_frame
        left_px, body_w = self._view.clip_rect_px(clip.start_frame, clip.end_frame)
        ow = max(1, int(round(self._view.width_px)))
        right_px = left_px + body_w
        zone = clip_edge_zone(
            x,
            left_px,
            body_w,
            _CLIP_TRIM_PX,
            left_visible=0 <= left_px <= ow,
            right_visible=0 <= right_px <= ow,
        )
        if zone == "outside":
            return "empty", seq_frame
        return zone, seq_frame

    def _on_track_pressed(self, track_idx: int, x: float, y: float, button: int, _mod: int) -> None:
        if not self._clip_ready() or self._sequence is None:
            return
        if button == _MOUSE_RIGHT:
            hit_x = self._strip_layout_x()
            if hit_x is None:
                hit_x = float(x)
            hit, _seq_frame = self._clip_hit(track_idx, hit_x)
            if hit == "empty":
                self._show_track_menu(track_idx, y)
            return
        if button != _MOUSE_LEFT:
            return
        self._sequence.selected_track = track_idx
        hit_x = self._strip_layout_x()
        if hit_x is None:
            hit_x = float(x)
        hit, seq_frame = self._clip_hit(track_idx, hit_x)
        if hit == "empty":
            self._sequence.playhead = seq_frame
            self._refresh_clips()
            self._refresh_playhead()
            return
        clip = self._sequence.tracks[track_idx].clip_at_sequence(seq_frame)
        if clip is None:
            return
        if hit == "body" and self._session.play_dir != 0:
            self._session.transport_stop()
        snap = Clip(
            id=clip.id,
            media_path=clip.media_path,
            start_frame=clip.start_frame,
            in_frame=clip.in_frame,
            out_frame=clip.out_frame,
            speed=clip.speed,
        )
        self._clip_drag_moved = False
        if hit == "body":
            self._clip_drag = ("move", track_idx, clip.id, snap, hit_x)
            self._move_drag_dest = track_idx
            self._move_drag_snap = snap
            self._move_feedback_sig = None
        elif hit == "trim_left":
            self._clip_drag = ("trim_left", track_idx, clip.id, snap, x)
        else:
            self._clip_drag = ("trim_right", track_idx, clip.id, snap, x)
        self._sync_cursor()
        self._refresh_clips()

    def _edge_delta(self, kind: str, snap: Clip, frame: int) -> int:
        """Frames to move the grabbed edge so it sits on ruler frame ``frame``."""
        if kind == "trim_left":
            return int(frame) - int(snap.start_frame)
        return (int(frame) - 1) - int(snap.end_frame)

    def _apply_edge_drag(self) -> None:
        """Move the grabbed edge to the ruler frame under the pointer. No seek."""
        if self._clip_drag is None or self._sequence is None or not self._clip_ready():
            return
        kind, ti, clip_id, snap, _x0 = self._clip_drag
        if kind not in ("trim_left", "trim_right"):
            return
        local = self._strip_layout_x()
        if local is None:
            return
        frame = self._view.frame_at_x(local)
        if self._stretch_mode:
            edge = "left" if kind == "trim_left" else "right"
            self._sequence.set_clip_speed_edge(ti, clip_id, snap, edge, frame)
        else:
            delta = self._edge_delta(kind, snap, frame)
            if kind == "trim_left":
                self._sequence.restore_and_trim_left(ti, clip_id, snap, delta)
            else:
                self._sequence.restore_and_trim_right(ti, clip_id, snap, delta)
        self._clip_drag_moved = True
        self._refresh_clips()

    def _finish_edge_drag(self) -> None:
        """Release keeps the last edge on the strip, then updates the preview once."""
        if self._clip_drag is None or self._clip_drag[0] not in ("trim_left", "trim_right"):
            return
        self._apply_edge_drag()
        self._clip_drag = None
        self._clip_drag_moved = False
        self._refresh_clips()
        self._commit_preview()
        self._sync_cursor()

    def _on_track_moved(self, track_idx: int, x: float, _y: float, _mod: int, _b: int) -> None:
        if self._clip_drag is None or not self._clip_ready() or self._sequence is None:
            return
        kind, _ti, _clip_id, _snap, _x0 = self._clip_drag
        if kind in ("trim_left", "trim_right"):
            self._apply_edge_drag()

    def _clear_move_feedback(self) -> None:
        for hi in self._track_drop_hilite:
            hi.visible = False
        for lead in self._track_ghost_leads:
            lead.visible = False
        for body in self._track_ghost_bodies:
            body.visible = False
        self._move_drag_dest = None
        self._move_feedback_sig = None

    def _move_status_text(self, text: str) -> None:
        if self._status is not None and text:
            self._status.text = text

    def _update_move_feedback(
        self,
        src_track: int,
        dest: int | None,
        snap: Clip,
        clip: Clip,
        want_start: int,
        ghost_start: int | None,
    ) -> None:
        for ti, hi in enumerate(self._track_drop_hilite):
            hi.visible = dest is not None and ti == dest and dest != src_track
        for ti in range(len(self._track_ghost_leads)):
            g_lead = self._track_ghost_leads[ti]
            g_body = self._track_ghost_bodies[ti]
            if dest is None or ti != dest or dest == src_track:
                g_lead.visible = False
                g_body.visible = False
                continue
            show_start = ghost_start if ghost_start is not None else want_start
            block_x, block_w = self._view.clip_rect_px(show_start, show_start + clip.duration - 1)
            g_lead.visible = True
            g_lead.width = ui.Pixel(max(0, block_x))
            g_body.visible = block_w >= 1
            g_body.width = ui.Pixel(max(block_w, 0))
            if ghost_start is None:
                g_body.style = _GHOST_NO_ROOM_STYLE
            elif ghost_start == want_start:
                g_body.style = _GHOST_OK_STYLE
            else:
                g_body.style = _GHOST_NUDGE_STYLE
        sig = (src_track, dest, want_start, ghost_start)
        if sig != self._move_feedback_sig:
            self._move_feedback_sig = sig

    def _apply_move_drag(self) -> None:
        if self._clip_drag is None or self._sequence is None or not self._clip_ready():
            return
        kind, ti, clip_id, snap, x0 = self._clip_drag
        if kind != "move":
            return
        if not self._mouse_left_down():
            self._finish_move_drag()
            return
        local = self._strip_layout_x()
        pos = self._pointer_over_strip()
        clip = self._sequence.tracks[ti].clip_by_id(clip_id)
        if clip is None or snap is None:
            return
        frame0 = self._view.frame_at_x(float(x0))
        if local is None:
            self._sequence.restore_clip_geometry(ti, clip_id, snap)
            dest: int | None = None
            want_start = int(snap.start_frame)
            ghost_start = None
        else:
            want = self._view.frame_at_x(local)
            want_start = int(snap.start_frame) + (want - frame0)
            fm = self._sequence.sequence_frame_max
            want_start = max(0, min(fm - clip.duration + 1, want_start))
            dest = self._track_index_at_strip_y(pos[1]) if pos is not None else ti
            if dest is None:
                self._sequence.restore_clip_geometry(ti, clip_id, snap)
                ghost_start = None
            elif dest == ti:
                self._sequence.set_clip_start(ti, clip_id, want_start)
                ghost_start = want_start
            else:
                self._sequence.restore_clip_geometry(ti, clip_id, snap)
                ghost_start = self._sequence.free_start_on_track(
                    dest, clip.duration, want_start, ignore_id=clip_id
                )
        self._move_drag_dest = dest if dest is not None else ti
        self._clip_drag_moved = want_start != snap.start_frame or (dest is not None and dest != ti)
        self._update_move_feedback(ti, dest, snap, clip, want_start, ghost_start)
        self._refresh_clips()

    def _finish_move_drag(self) -> None:
        if self._clip_drag is None or self._clip_drag[0] != "move" or self._sequence is None:
            return
        ti, clip_id, snap, x0 = (
            self._clip_drag[1],
            self._clip_drag[2],
            self._clip_drag[3],
            self._clip_drag[4],
        )
        local = self._strip_layout_x()
        pos = self._pointer_over_strip()
        clip = self._sequence.tracks[ti].clip_by_id(clip_id)
        self._clip_drag = None
        status = ""
        if clip is None or snap is None:
            self._clear_move_feedback()
            self._refresh_clips()
            return
        if local is None or pos is None:
            self._sequence.restore_clip_geometry(ti, clip_id, snap)
            status = "Move cancelled"
        else:
            want = self._view.frame_at_x(local)
            frame0 = self._view.frame_at_x(float(x0))
            want_start = int(snap.start_frame) + (want - frame0)
            fm = self._sequence.sequence_frame_max
            want_start = max(0, min(fm - clip.duration + 1, want_start))
            dest = self._track_index_at_strip_y(pos[1])
            if dest is None:
                self._sequence.restore_clip_geometry(ti, clip_id, snap)
                status = "Move cancelled"
            elif dest == ti:
                self._sequence.set_clip_start(ti, clip_id, want_start)
            else:
                reason, landed = self._sequence.move_clip(clip_id, dest, want_start)
                if reason == "no_room":
                    self._sequence.restore_clip_geometry(ti, clip_id, snap)
                    status = "No room on T{}".format(dest + 1)
                elif reason == "ok" and landed is not None and landed != want_start:
                    status = "Nudged to frame {} on T{}".format(landed, dest + 1)
        self._clear_move_feedback()
        self._clip_drag_moved = False
        self._refresh_clips()
        self._refresh_track_headers()
        self._commit_preview()
        self._sync_cursor()
        if status and self._status is not None:
            self._status.text = status

    def _on_track_released(self, track_idx: int, x: float, y: float, button: int, _mod: int) -> None:
        if button != _MOUSE_LEFT or self._clip_drag is None or self._sequence is None:
            return
        kind, ti, _clip_id, _snap, _x0 = self._clip_drag
        if kind in ("trim_left", "trim_right"):
            self._finish_edge_drag()
            return
        if kind == "move":
            if not self._clip_drag_moved:
                hit_x = self._strip_layout_x()
                if hit_x is None:
                    hit_x = float(x)
                hit, seq_frame = self._clip_hit(ti, hit_x)
                self._clip_drag = None
                self._clear_move_feedback()
                if hit == "body":
                    self._seek_sequence(seq_frame, scrub_begin=True, scrub_change=True, scrub_end=True)
                else:
                    self._refresh_clips()
                return
            self._finish_move_drag()
            return
        self._clip_drag = None
        self._clip_drag_moved = False
        self._refresh_clips()
        self._commit_preview()

    def _on_full_released(self, _x: float, _y: float, button: int, _mod: int) -> None:
        if button == _MOUSE_LEFT:
            self._full_drag = None
            self._sync_cursor()

    def _on_session_sequence(self, seq: int) -> None:
        if self._closed or self._session.play_dir == 0:
            return
        if self._full_drag is not None or self._clip_drag is not None:
            return
        if self._sequence is not None:
            self._sequence.playhead = int(seq)
        self._view.follow(self._sequence_playhead(), self._session.play_dir)
        self._refresh_viewport()
        self._refresh_playhead()

    def _apply_clip_path(self, path: str) -> None:
        if self._closed:
            return
        if path:
            self._path_field.model.set_value(path)
        idx = fixture_index_for_path(path) if path else None
        if idx is not None:
            self._fixture_combo.model.get_item_value_model().set_value(idx)
        info = self._session.clip_info
        if info:
            self._on_clip_opened(int(info["frames"]))

    def _on_clip_opened(self, frames: int) -> None:
        self._sync_fps()
        path = self._session.clip_path or self._path_field.model.get_value_as_string().strip()
        rows_before = len(self._cell_gaps)
        track_count = self._load_track_count()
        self._sequence = Sequence.from_opened_media(path, int(frames), track_count=track_count)
        self._configure_timeline_for_session()
        self._view.set_frame_count(self._timeline_frame_count())
        self._clip_drag = None
        self._vp_sig = None
        self._grid_sig = None
        self._on_strip_width()
        self._restore_saved_zoom()
        self._refresh_viewport()
        if len(self._sequence.tracks) != rows_before:
            self._rebuild_rows()
        else:
            self._refresh_track_headers()

    def _sync_ui_from_session(self) -> None:
        path = self._session.clip_path
        if not path:
            path = str(carb.settings.get_settings().get("/exts/v1d.cor/clip") or "").strip()
        if path:
            self._apply_clip_path(path)
        info = self._session.clip_info
        if info:
            self._on_clip_opened(int(info["frames"]))

    def _on_open_clicked(self) -> None:
        path = self._path_field.model.get_value_as_string().strip()
        if not path:
            return
        try:
            info = self._session.open_clip(path)
            self._on_clip_opened(int(info["frames"]))
        except Exception as exc:  # noqa: BLE001
            carb.log_error(f"[v1d.tl] open_clip: {exc}")
            if self._status is not None:
                self._status.text = str(exc)

    def _on_fixture_changed(self, model, _item) -> None:
        idx = model.get_item_value_model().get_value_as_int()
        if idx < 0 or idx >= len(S4_FIXTURE_CHOICES):
            return
        name, _label = S4_FIXTURE_CHOICES[idx]
        path = fixture_path(name)
        self._path_field.model.set_value(str(path))
        try:
            info = self._session.open_fixture(name)
            self._on_clip_opened(int(info["frames"]))
        except Exception as exc:  # noqa: BLE001
            carb.log_error(f"[v1d.tl] fixture {name}: {exc}")
            if self._status is not None:
                self._status.text = str(exc)

    def _can_cut_at_playhead(self) -> bool:
        if not self._clip_ready() or self._sequence is None:
            return False
        ti = max(0, min(len(self._sequence.tracks) - 1, int(self._sequence.selected_track)))
        ph = self._sequence_playhead()
        clip = self._sequence.tracks[ti].clip_at_sequence(ph)
        if clip is None:
            return False
        return ph > clip.start_frame

    def _sync_scissor_enabled(self) -> None:
        btn = getattr(self, "_scissor_btn", None)
        if btn is None:
            return
        btn.enabled = self._can_cut_at_playhead()

    def _on_scissor(self) -> None:
        if not self._clip_ready() or self._sequence is None:
            return
        if self._session.play_dir != 0:
            self._session.transport_stop()
        ti = max(0, min(len(self._sequence.tracks) - 1, int(self._sequence.selected_track)))
        reason, _new_id = self._sequence.cut_at(ti, self._sequence_playhead())
        if reason != "ok":
            if self._status is not None:
                self._status.text = f"Cut: {reason}"
            return
        self._refresh_clips()
        self._commit_preview()
        self._sync_scissor_enabled()

    def _on_stretch_toggle(self) -> None:
        self._stretch_mode = not self._stretch_mode
        if self._clock_btn is not None:
            self._clock_btn.style = _TOGGLE_ON_STYLE if self._stretch_mode else {}
        self._sync_cursor()

    def _register_project_hooks(self) -> None:
        from v1d.kit import project_hooks

        project_hooks.register("new", self._project_new)
        project_hooks.register("open", self._project_open)
        project_hooks.register("save", self._project_save)
        project_hooks.register("is_dirty", self._project_is_dirty)
        project_hooks.register("add_video", self._add_video_files)
        project_hooks.register("get_render_state", self._project_render_state)

    def _unregister_project_hooks(self) -> None:
        from v1d.kit import project_hooks

        for name in ("new", "open", "save", "is_dirty", "add_video", "get_render_state"):
            project_hooks.unregister(name)

    def _project_is_dirty(self) -> bool:
        if self._sequence is None:
            return False
        return self._sequence.dirty_generation != self._dirty_baseline

    def _project_continue(self, then) -> None:
        if not self._project_is_dirty():
            then()
            return

        def chosen(choice: str) -> None:
            if choice == "cancel":
                return
            if choice == "save":
                self._project_save()
                if self._project_is_dirty():
                    return
            then()

        self._show_save_prompt(chosen)

    def _show_save_prompt(self, on_choice) -> None:
        flags = (
            ui.WINDOW_FLAGS_MODAL
            | ui.WINDOW_FLAGS_NO_RESIZE
            | ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_DOCKING
        )
        win = ui.Window(
            "Unsaved project",
            width=440,
            height=120,
            flags=flags,
            dockPreference=ui.DockPreference.DISABLED,
            visible=True,
        )
        self._save_prompt = win
        answered = {"done": False}

        def choose(value: str) -> None:
            if answered["done"]:
                return
            answered["done"] = True
            win.visible = False
            on_choice(value)

        win.set_visibility_changed_fn(lambda vis: choose("cancel") if not vis else None)
        with win.frame:
            with ui.VStack(spacing=10, height=0):
                ui.Spacer(height=8)
                ui.Label("Save changes before continuing?", height=22, alignment=ui.Alignment.CENTER)
                ui.Spacer(height=6)
                with ui.HStack(spacing=8, height=28):
                    ui.Spacer()
                    ui.Button("Save", width=88, clicked_fn=lambda: choose("save"))
                    ui.Button("Discard", width=88, clicked_fn=lambda: choose("discard"))
                    ui.Button("Cancel", width=88, clicked_fn=lambda: choose("cancel"))
                    ui.Spacer()

    def _project_build_state(self) -> dict:
        base = None
        if self._project_path:
            base = Path(self._project_path).parent
        state = self._sequence.to_dict(base) if self._sequence else Sequence.empty().to_dict(base)
        state["view"] = {"zoom_percent": self._zoom_percent()}
        if self._project_path:
            state["project_path"] = self._project_path
        return state

    def _project_render_state(self) -> dict | None:
        if self._sequence is None:
            return None
        import copy

        return copy.deepcopy(self._project_build_state())

    def _apply_loaded_state(self, data: dict, base_dir: Path) -> None:
        self._sequence = Sequence.from_dict(data, base_dir)
        view = data.get("view") or {}
        zoom = float(view.get("zoom_percent", 100.0))
        self._configure_timeline_for_session()
        self._view.set_frame_count(self._timeline_frame_count())
        self._view.set_zoom_percent(zoom, center=False)
        self._clip_drag = None
        self._vp_sig = None
        self._grid_sig = None
        self._rebuild_rows()
        self._refresh_track_headers()
        self._refresh_clips()
        self._commit_preview()
        self._sequence.mark_clean()
        self._dirty_baseline = 0
        self._sync_dirty_title()

    def _project_new(self) -> None:
        self._project_new_now()

    def _proxy_cache_dir(self) -> Path:
        import os

        xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
        if xdg:
            return Path(xdg) / "v1d" / "proxy"
        return Path.home() / ".cache" / "v1d" / "proxy"

    def _drop_imported_proxy(self, paths: list[str]) -> None:
        root = self._proxy_cache_dir()
        if not root.is_dir():
            return
        for raw in paths:
            if not raw:
                continue
            key = str(Path(raw).resolve()) if Path(raw).is_file() else raw
            digest = 14695981039346656037
            for byte in key.encode():
                digest ^= byte
                digest = (digest * 1099511628211) & 0xFFFFFFFFFFFFFFFF
            prefix = f"{digest:x}_"
            for cached in root.glob(prefix + "*.v1dproxy"):
                try:
                    cached.unlink()
                except OSError as exc:
                    carb.log_warn(f"[v1d.tl] proxy cache: {exc}")

    def _project_new_now(self) -> None:
        paths: list[str] = []
        if self._sequence is not None:
            for track in self._sequence.tracks:
                for clip in track.clips:
                    if clip.media_path:
                        paths.append(clip.media_path)
        current = self._session.clip_path
        if current:
            paths.append(current)
        self._clip_drag = None
        self._header_drag = None
        prompt = getattr(self, "_save_prompt", None)
        if prompt is not None:
            prompt.visible = False
        try:
            self._session.release_media_async(paths, self._drop_imported_proxy)
            old_rows = self._ui_row_count()
            track_count = self._load_track_count()
            self._sequence = Sequence.empty(track_count=track_count)
            self._sequence.mark_clean()
            self._project_path = None
            self._dirty_baseline = 0
            self._path_field.model.set_value("")
            self._view.set_frame_count(self._timeline_frame_count())
            if track_count == old_rows:
                # Rebuilding rows in the same frame as the preview blank reset the GPU
                # (repro: tools in /tmp bisect). Hide the blocks in place instead.
                for slots in self._clip_slots:
                    for slot in slots:
                        self._hide_clip_slot(slot)
                self._refresh_track_headers()
            else:
                self._rebuild_rows()
            self._sync_dirty_title()
            if self._status is not None:
                self._status.text = "New project"
        except Exception as exc:  # noqa: BLE001
            carb.log_error(f"[v1d.tl] new project: {exc}")
            if self._status is not None:
                self._status.text = str(exc)

    def _project_open(self) -> None:
        self._project_continue(self._project_open_now)

    def _project_open_now(self) -> None:
        from v1d.kit import dialogs
        from v1d.tl.project import load_project

        path = dialogs.pick_open_v1d()
        if not path:
            return
        try:
            data, base = load_project(path)
            self._project_path = path
            self._apply_loaded_state(data, base)
            if self._status is not None:
                self._status.text = f"Opened {Path(path).name}"
        except Exception as exc:  # noqa: BLE001
            carb.log_error(f"[v1d.tl] open project: {exc}")
            if self._status is not None:
                self._status.text = str(exc)

    def _project_save(self) -> None:
        from v1d.kit import dialogs
        from v1d.tl.project import save_project

        if self._sequence is None:
            return
        path = self._project_path
        if not path:
            picked = dialogs.pick_save_v1d()
            if not picked:
                return
            path = picked if picked.endswith(".v1d") else f"{picked}.v1d"
            self._project_path = path
        base = Path(path).parent
        state = self._project_build_state()
        try:
            save_project(path, state)
            self._sequence.mark_clean()
            self._dirty_baseline = self._sequence.dirty_generation
            self._sync_dirty_title()
            if self._status is not None:
                self._status.text = f"Saved {Path(path).name}"
        except Exception as exc:  # noqa: BLE001
            carb.log_error(f"[v1d.tl] save project: {exc}")

    def _accepted_video_path(self, path: str) -> bool:
        p = path.strip().lower()
        return p.endswith((".mp4", ".mov", ".m4v"))

    def _import_video_paths(
        self, paths: list[str], x: float | None, y: float | None, *, extend: bool = False
    ) -> None:
        if not paths or self._sequence is None:
            return
        ti = int(self._sequence.selected_track)
        if x is not None and y is not None:
            dest = self._track_index_at_strip_y(y)
            if dest is not None:
                ti = dest
        want = 0
        if x is not None:
            hit = self._strip_layout_x()
            if hit is not None:
                want = self._view.frame_at_x(hit)
        for raw in paths:
            if not self._accepted_video_path(raw):
                if self._status is not None:
                    self._status.text = "Unsupported container (use MP4/MOV/M4V)"
                continue
            path = str(Path(raw).resolve())
            try:
                self._session.ensure_media_path(path)
                info = self._session.clip_info
                if not info:
                    continue
                frames = int(info["frames"])
                reason, clip = self._sequence.add_clip(ti, path, frames, want, extend=extend)
                if reason != "ok" or clip is None:
                    if self._status is not None:
                        self._status.text = f"Import: {reason}"
                    continue
                want = clip.end_frame + 1
                if extend and self._status is not None:
                    self._status.text = f"Dropped on T{ti + 1} at frame {clip.start_frame}"
            except Exception as exc:  # noqa: BLE001
                carb.log_error(f"[v1d.tl] import {path}: {exc}")
                if self._status is not None:
                    self._status.text = str(exc)
                continue
        self._refresh_clips()
        self._refresh_track_headers()
        self._commit_preview()
        self._sync_scissor_enabled()

    def _add_video_files(self) -> None:
        from v1d.kit import dialogs

        path = dialogs.pick_open_video()
        if path:
            self._import_video_paths([path], None, None)

    def _on_window_drop(self, event) -> None:
        """OS file drop (file manager -> Kit window). The event carries paths only,
        so the target track and frame come from the pointer at release."""
        if getattr(self, "_closed", True) or getattr(self, "_sequence", None) is None:
            return
        try:
            raw_paths = [str(p) for p in event.payload["paths"]]
        except Exception as exc:  # noqa: BLE001
            carb.log_warn(f"[v1d.tl] drop payload: {exc!r}")
            return
        paths = [_drop_path(p) for p in raw_paths]
        pos = self._pointer_over_strip()
        if pos is None or self._track_index_at_strip_y(pos[1]) is None:
            if self._status is not None:
                self._status.text = "Drop a video onto a track row in the timeline"
            return
        self._import_video_paths(paths, pos[0], pos[1], extend=True)

    def _wire_strip_drop(self, strip_frame: ui.Frame) -> None:
        if not hasattr(strip_frame, "set_drop_fn"):
            return

        def _on_drop(*args):
            paths: list[str] = []
            x = y = None
            for a in args:
                if isinstance(a, str) and ("/" in a or "\\" in a):
                    paths.append(a)
                elif isinstance(a, (list, tuple)):
                    for item in a:
                        if isinstance(item, str):
                            paths.append(item)
            if len(args) >= 2 and isinstance(args[0], (int, float)):
                x, y = float(args[0]), float(args[1])
            if paths:
                self._import_video_paths(paths, x, y)

        try:
            strip_frame.set_drop_fn(_on_drop)
        except Exception as exc:  # noqa: BLE001
            carb.log_warn(f"[v1d.tl] strip drop_fn not available: {exc}")
        accept = getattr(strip_frame, "set_accept_drop_fn", None)
        if accept is not None:
            try:
                accept(lambda *_a: True)
            except Exception:  # noqa: BLE001
                pass

    def _on_start(self) -> None:
        if self._clip_ready():
            self._seek_sequence(0)

    def _on_end(self) -> None:
        if self._clip_ready() and self._sequence is not None:
            self._seek_sequence(self._sequence.sequence_frame_max)

    def _on_step(self, direction: int) -> None:
        if self._clip_ready():
            self._seek_sequence(self._sequence_playhead() + direction)

    def _on_play(self, direction: int) -> None:
        if self._clip_ready():
            if self._session.play_dir == direction:
                self._session.transport_stop()
                return
            self._start_transport(direction)

    def _on_pause(self) -> None:
        if self._clip_ready():
            self._session.transport_stop()

    def _on_stop(self) -> None:
        if self._clip_ready():
            self._session.transport_stop()
            self._seek_sequence(0)

    def _on_zoom(self, factor: float) -> None:
        if not self._clip_ready():
            return
        self._on_strip_width()
        if self._view.width_px < 1.0:
            return
        self._view.zoom(factor, self._view.anchor_frame(self._sequence_playhead()))
        self._grid_sig = None
        self._vp_sig = None
        self._refresh_viewport()
        self._save_zoom_percent()

    def _on_fit(self) -> None:
        if not self._clip_ready():
            return
        self._view.fit()
        self._grid_sig = None
        self._vp_sig = None
        self._refresh_viewport()
        self._refresh_grid()
        self._save_zoom_percent()

    def _on_wheel(self, _x: float, _y: float, _mod: int) -> None:
        if self._closed or self._full_drag is not None:
            return
        iinput = carb.input.acquire_input_interface()
        mouse = omni.appwindow.get_default_app_window().get_mouse()
        up = float(iinput.get_mouse_value(mouse, carb.input.MouseInput.SCROLL_UP))
        down = float(iinput.get_mouse_value(mouse, carb.input.MouseInput.SCROLL_DOWN))
        zoom_in = wheel_zoom_direction(up, down, self._wheel_up, self._wheel_down)
        self._wheel_up = up
        self._wheel_down = down
        if zoom_in is None:
            return
        now = time.monotonic()
        if now - self._wheel_at < _WHEEL_ZOOM_MIN_S:
            return
        self._wheel_at = now
        if not self._clip_ready():
            return
        self._on_strip_width()
        if self._view.width_px < 1.0:
            return
        pct = self._zoom_percent()
        lo = self._view.min_zoom_percent()
        target = next_wheel_zoom_percent(
            pct, zoom_in, step_pct=_WHEEL_ZOOM_STEP_PCT, lo_pct=lo
        )
        if target is None:
            return
        hover_x = self._strip_pointer_local_x()
        hover_frame = self._view.frame_at_x(hover_x)
        self._view.set_zoom_percent(target, hover_frame, center=True)
        self._grid_sig = None
        self._vp_sig = None
        self._refresh_viewport()
        self._save_zoom_percent()

    def _sync_transport_blink(self) -> None:
        play = getattr(self, "_play_btn", None)
        rev = getattr(self, "_reverse_btn", None)
        if play is None or rev is None:
            return
        direction = 0
        session = getattr(self, "_session", None)
        if session is not None:
            try:
                direction = int(session.play_dir)
            except Exception:
                direction = 0
        phase = int(time.monotonic() * 2.5) % 2 if direction else 0
        sig = (direction, phase)
        if sig == getattr(self, "_blink_sig", None):
            return
        self._blink_sig = sig
        dim = 0xFF2A2A2A
        lit = 0xFF8A8A8A

        def face(btn: ui.Button, active: bool) -> None:
            btn.style = {"background_color": (lit if phase else dim) if active else dim}

        face(rev, direction < 0)
        face(play, direction > 0)

    def _on_update(self, _e) -> None:
        if self._closed or self._status is None:
            return
        self._sync_transport_blink()
        if self._playhead_drag:
            if not self._mouse_left_down():
                self._finish_playhead_drag()
            else:
                frame = self._playhead_frame_under_grab()
                if frame is not None and frame != self._sequence_playhead():
                    self._seek_sequence(frame, scrub_change=True)
        if self._clip_drag is not None:
            kind = self._clip_drag[0]
            if kind in ("trim_left", "trim_right"):
                if not self._mouse_left_down():
                    self._finish_edge_drag()
                else:
                    self._apply_edge_drag()
                self._sync_cursor()
                self._refresh_clips()
                self._refresh_playhead()
                return
            if kind == "move":
                if not self._mouse_left_down():
                    self._finish_move_drag()
                else:
                    self._apply_move_drag()
                self._sync_cursor()
                self._refresh_playhead()
                return
        if self._view.width_px < 1.0:
            self._on_strip_width()
        self._refresh_viewport()
        self._refresh_grid()
        self._refresh_clips()
        self._refresh_playhead()
        if not self._clip_ready():
            return
        self._sync_cursor()
        n = self._view.frames_per_cell()
        unit = "frame" if n == 1 else "frames"
        zoom = self._zoom_percent()
        zoom_text = f"{zoom:.0f}%" if abs(zoom - round(zoom)) < 0.05 else f"{zoom:.1f}%"
        if self._zoom_label is not None:
            self._zoom_label.text = zoom_text
        self._status.text = f"{self._session.last_status}  |  zoom {zoom_text}  |  1 cell = {n} {unit}"

    def _zoom_percent(self) -> float:
        """100% is the whole sequence. 30 frames of 600 is 5%."""
        return self._view.zoom_percent()

    def on_shutdown(self) -> None:
        self._closed = True
        self._unregister_project_hooks()
        if self._track_menu is not None:
            try:
                self._track_menu.hide()
            except Exception:
                pass
            self._track_menu = None
        self._sub = None
        self._drop_sub = None
        if self._kb_sub is not None and self._kb_device is not None:
            carb.input.acquire_input_interface().unsubscribe_to_keyboard_events(self._kb_device, self._kb_sub)
            self._kb_sub = None
            self._kb_device = None
        session = getattr(self, "_session", None)
        if session is not None:
            session.remove_sequence_listener(self._on_session_sequence)
            session.clear_timeline()
            session.remove_clip_path_listener(self._apply_clip_path)
        self._pan_lead = None
        self._pan_thumb = None
        self._pan_tail = None
        self._full_input = None
        if self._cursor_kind != "arrow":
            self._cursor_kind = ""
            self._sync_cursor()
        self._cell_gaps = []
        self._cell_bodies = []
        self._grid_leads = []
        self._grid_tails = []
        self._ruler_frame = None
        self._play_head_frame = None
        self._playhead_mark_x = None
        self._playhead_drag = False
        self._clock = None
        self._full_play_lead = None
        self._full_play_tail = None
        self._detail_play_frame = None
        self._lens_leads = []
        self._lens_bodies = []
        self._lens_tails = []
        self._track_clip_leads = []
        self._track_clip_tails = []
        self._track_clip_bodies = []
        self._track_clip_labels = []
        self._track_clip_label_leads = []
        self._track_clip_edge_leads = []
        self._track_clip_edge_gaps = []
        self._track_clip_edge_l = []
        self._track_clip_edge_r = []
        self._clip_slots = []
        self._track_drop_hilite = []
        self._track_ghost_leads = []
        self._track_ghost_bodies = []
        self._track_rows_frame = None
        self._track_header_frame = None
        self._detail_strip_zstack = None
        self._time_pane_hstack = None
        self._track_titles = []
        self._track_eyes = []
        self._track_speakers = []
        self._header_drag = None
        self._sequence = None
        self._clip_drag = None
        self._strip_frame = None
        if getattr(self, "_window", None):
            unwire_window_menu(self, getattr(self, "_window_title", WINDOW_TITLE))
            self._window.visible = False
