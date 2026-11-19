# SPDX-License-Identifier: MIT
"""Offline composition render — GPU frames via ScrubSession, NVENC mux (ffmpeg)."""

from __future__ import annotations

import pathlib
import subprocess
import tempfile
import time
from dataclasses import dataclass

from v1d.kit import project_hooks
from v1d.ngn import _scrub
from v1d.ngn.session import ScrubSession
from v1d.rnd.png_io import write_rgba_png


@dataclass
class RenderProgress:
    state: str
    frames_done: int
    frames_total: int
    fps: float
    message: str


def _load_sequence_mod():
    import importlib.util
    import sys

    root = pathlib.Path(__file__).resolve().parents[5]
    path = root / "source/extensions/v1d.tl/python/v1d/tl/sequence.py"
    spec = importlib.util.spec_from_file_location("v1d_tl_sequence_rnd", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _span_from_state(data: dict) -> tuple[int, int]:
    seq_mod = _load_sequence_mod()
    base = None
    pp = data.get("project_path")
    if pp:
        base = pathlib.Path(pp).parent
    seq = seq_mod.Sequence.from_dict(data, base)
    span = seq.sequence_playback_span()
    if span is None:
        return (0, 0)
    return span


def _write_latest_png(session: ScrubSession, path: pathlib.Path, w: int, h: int) -> bool:
    latest = session.latest_present()
    if not latest:
        return False
    pw, ph = int(latest["width"]), int(latest["height"])
    ptr, stride = _scrub.cuda_alloc_rgba(pw, ph)
    try:
        if not session.copy_latest_rgba_to(ptr, stride):
            return False
        rgba = _scrub.cuda_read_rgba(int(ptr), pw, ph, int(stride))
        write_rgba_png(str(path), pw, ph, rgba, int(stride))
        return True
    finally:
        _scrub.cuda_free(ptr)


def run_render(
    out_path: pathlib.Path,
    fps: float,
    *,
    cancel_flag: list[bool],
    progress_cb,
) -> tuple[bool, str]:
    state = project_hooks.call("get_render_state")
    if not state:
        return False, "No composition (open or create a project)"
    lo, hi = _span_from_state(state)
    if hi < lo:
        return False, "Nothing to render"
    total = hi - lo + 1
    session = ScrubSession.get()
    if not session.clip_info:
        return False, "Open at least one video file first"

    seq_mod = _load_sequence_mod()
    base = pathlib.Path(state.get("project_path") or ".").parent
    seq = seq_mod.Sequence.from_dict(state, base)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v1d-rnd-") as tmp:
        tmp_p = pathlib.Path(tmp)
        t0 = time.perf_counter()
        w, h = 960, 540
        for i, frame in enumerate(range(lo, hi + 1)):
            if cancel_flag and cancel_flag[0]:
                return False, "Cancelled"
            png = tmp_p / f"{i:06d}.png"
            clip = seq.preview_clip(frame)
            wrote = False
            if clip is not None:
                try:
                    session.ensure_media_path(clip.media_path)
                    src = clip.source_at(frame)
                    if src is not None:
                        session.engine.set_scrubbing(False)
                        session.engine.set_playback(False)
                        session.engine.request_frame(int(src))
                        deadline = time.perf_counter() + 8.0
                        while time.perf_counter() < deadline:
                            meta = session.poll_frame()
                            if meta and int(meta.get("frame", -1)) == int(src):
                                break
                            time.sleep(0.002)
                        wrote = _write_latest_png(session, png, w, h)
                except Exception:  # noqa: BLE001
                    wrote = False
            if not wrote:
                write_rgba_png(str(png), w, h, bytes([0, 0, 0, 255]) * (w * h))
            if progress_cb:
                elapsed = max(1e-6, time.perf_counter() - t0)
                progress_cb(
                    RenderProgress(
                        state="running",
                        frames_done=i + 1,
                        frames_total=total,
                        fps=(i + 1) / elapsed,
                        message="",
                    )
                )

        if cancel_flag and cancel_flag[0]:
            return False, "Cancelled"
        part = out_path.with_suffix(out_path.suffix + ".part")
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(fps),
            "-i",
            str(tmp_p / "%06d.png"),
            "-c:v",
            "h264_nvenc",
            "-pix_fmt",
            "yuv420p",
            str(part),
        ]
        try:
            subprocess.run(cmd, check=True, timeout=3600)
        except FileNotFoundError:
            return False, "ffmpeg not found"
        except subprocess.CalledProcessError as exc:
            return False, f"ffmpeg encode failed: {exc}"
        if part.is_file():
            part.replace(out_path)
    return True, str(out_path)