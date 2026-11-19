# SPDX-License-Identifier: MIT
"""Render options. Pure unless carb imports; tests do not need Kit."""

from __future__ import annotations

import math
import pathlib
from dataclasses import dataclass

_PREFIX = "/persistent/exts/v1d.rnd/"
_CODECS = ("h264", "hevc")
CQ_MIN = 15
CQ_MAX = 35

# ~5 Mbps at 1920×1080, 30 fps, CQ 23, H.264. Lower CQ → higher bitrate.
_BITS_PER_PIXEL = 0.08
_HEVC_SCALE = 0.65


def _carb_settings():
    """Settings handle, or None when carb does not import (unit tests)."""
    try:
        import carb
    except ImportError:
        return None
    settings_api = getattr(carb, "settings", None)
    get_settings = getattr(settings_api, "get_settings", None)
    if not callable(get_settings):
        return None
    try:
        return get_settings()
    except Exception:
        return None


def _integral(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def _parse_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off"):
            return False
    return None


@dataclass
class RenderOptions:
    folder: str = ""
    filename: str = "v1d_render.mp4"
    codec: str = "h264"
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    cq: int = 23
    overwrite: bool = False

    def resolved_filename(self) -> str:
        name = (self.filename or "").strip() or "v1d_render.mp4"
        if not name.endswith(".mp4"):
            name += ".mp4"
        return name

    def output_path(self) -> pathlib.Path:
        folder = pathlib.Path((self.folder or "").strip()).expanduser()
        return folder / self.resolved_filename()

    def bitrate_bps(self) -> float:
        """Bits per second. Falls as CQ rises; HEVC is a fraction of H.264."""
        try:
            pixels = float(self.width) * float(self.height)
            fps = float(self.fps)
            cq = float(self.cq)
        except (TypeError, ValueError):
            return 0.0
        if not all(math.isfinite(v) for v in (pixels, fps, cq)):
            return 0.0
        if pixels <= 0.0 or fps <= 0.0:
            return 0.0
        quality = (float(CQ_MAX + 1) - cq) / float(CQ_MAX + 1 - 23)
        if quality <= 0.0:
            return 0.0
        scale = _HEVC_SCALE if self.codec == "hevc" else 1.0
        return pixels * fps * _BITS_PER_PIXEL * quality * scale

    def estimate_bytes(self, seconds: float) -> int:
        """Byte size for `seconds` of video. Grows with bitrate and duration."""
        try:
            span = float(seconds)
        except (TypeError, ValueError):
            return 0
        if not math.isfinite(span) or span <= 0.0:
            return 0
        return int(self.bitrate_bps() * span / 8.0)

    def validate(self) -> str | None:
        """Error text, or None when a render may start."""
        folder = self.folder if isinstance(self.folder, str) else ""
        if not folder.strip():
            return "Pick an output folder"
        if self.codec not in _CODECS:
            return "Codec must be h264 or hevc"
        width = _integral(self.width)
        height = _integral(self.height)
        if (
            width is None
            or height is None
            or width <= 0
            or height <= 0
            or width % 2
            or height % 2
        ):
            return "Width and height must be positive even numbers"
        cq = _integral(self.cq)
        if cq is None or cq < CQ_MIN or cq > CQ_MAX:
            return f"CQ must be from {CQ_MIN} to {CQ_MAX}"
        try:
            fps = float(self.fps)
        except (TypeError, ValueError):
            fps = 0.0
        if not math.isfinite(fps) or fps <= 0.0:
            return "Frame rate must be positive"
        if not isinstance(self.overwrite, bool):
            return "Overwrite must be true or false"
        if self.output_path().is_file() and not self.overwrite:
            return "Output exists — change the file name"
        return None


def default_options() -> RenderOptions:
    return RenderOptions(folder=str(pathlib.Path.home() / "Videos"))


def load_options() -> RenderOptions:
    """Last saved options, or defaults when carb is unavailable."""
    opts = default_options()
    settings = _carb_settings()
    if settings is None:
        return opts
    folder = settings.get(_PREFIX + "folder")
    if isinstance(folder, str) and folder.strip():
        opts.folder = folder.strip()
    filename = settings.get(_PREFIX + "filename")
    if isinstance(filename, str) and filename.strip():
        opts.filename = filename.strip()
    codec = settings.get(_PREFIX + "codec")
    if isinstance(codec, str) and codec in _CODECS:
        opts.codec = codec
    width = _integral(settings.get(_PREFIX + "width"))
    if width is not None and width > 0:
        opts.width = width
    height = _integral(settings.get(_PREFIX + "height"))
    if height is not None and height > 0:
        opts.height = height
    try:
        fps = float(settings.get(_PREFIX + "fps"))
    except (TypeError, ValueError):
        fps = None
    if fps is not None and math.isfinite(fps) and fps > 0.0:
        opts.fps = fps
    cq = _integral(settings.get(_PREFIX + "cq"))
    if cq is not None:
        opts.cq = cq
    overwrite = _parse_bool(settings.get(_PREFIX + "overwrite"))
    if overwrite is not None:
        opts.overwrite = overwrite
    return opts


def save_options(opts: RenderOptions) -> None:
    """Write last options under `/persistent/exts/v1d.rnd/` when carb imports."""
    settings = _carb_settings()
    if settings is None:
        return
    settings.set(_PREFIX + "folder", str(opts.folder))
    settings.set(_PREFIX + "filename", str(opts.filename))
    settings.set(_PREFIX + "codec", str(opts.codec))
    settings.set(_PREFIX + "width", int(opts.width))
    settings.set(_PREFIX + "height", int(opts.height))
    settings.set(_PREFIX + "fps", float(opts.fps))
    settings.set(_PREFIX + "cq", int(opts.cq))
    settings.set_bool(_PREFIX + "overwrite", bool(opts.overwrite))
