# SPDX-License-Identifier: MIT
"""Shared engine + playback state for v1d.pv / v1d.tl (and legacy single-window UI)."""

from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

import carb

from v1d.ngn import Engine
from v1d.ngn.fixtures import fixture_path

FrameFn = Callable[[int], None]
SequenceFn = Callable[[int], None]
SourceAtSequenceFn = Callable[[int], int | None]
MediaAtSequenceFn = Callable[[int], str | None]
ClipPathFn = Callable[[str], None]
BlankFn = Callable[[], None]
AfterCloseFn = Callable[[list[str]], None]

T = TypeVar("T")

# Timeline arrows: tap is shorter than this; hold-forward play uses this threshold (PLAN_04_TL_SLIDER).
ARROW_HOLD_S = 0.25


def _even_down(v: int) -> int:
    return v & ~1 if v > 0 else 0


class ScrubSession:
    _instance: ScrubSession | None = None

    @classmethod
    def get(cls) -> ScrubSession:
        if cls._instance is None:
            cls._instance = ScrubSession()
        return cls._instance

    def __init__(self) -> None:
        self._engine: Engine | None = None
        self._clip_info: dict | None = None
        self._last_request = 0
        self._play_dir = 0
        self._play_pos = 0.0
        self._play_t_last = 0.0
        self._arrow_key_down = 0
        self._arrow_t_down = 0.0
        self._arrow_stepped_frame = 0
        self._arrow_play_origin = 0
        self._arrow_play_t0 = 0.0
        self._play_emit_frame = 0
        self._arrow_hold_promoted = False
        self._frame_listeners: list[FrameFn] = []
        self._sequence_listeners: list[SequenceFn] = []
        self._clip_path_listeners: list[ClipPathFn] = []
        self._listener_fail_logged: set[int] = set()
        self._clip_path = ""
        self._fatbin = ""
        self._device = 0
        self._cache_mb = 0
        self._proxy_height = 270
        self._proxy_vram_mb = 256
        self._last_status = "Open a clip"
        self._preview_gap = False
        self._timeline_mode = False
        self._timeline_seq_lo = 0
        self._timeline_seq_hi = 0
        self._timeline_source_at: SourceAtSequenceFn | None = None
        self._timeline_media_at: MediaAtSequenceFn | None = None
        self._last_emitted_src: int | None = None
        self._out_w = 0
        self._out_h = 0
        self._stats_cache: dict = {}
        self._stats_t = 0.0
        self._audio = None
        self._blank_listeners: list[BlankFn] = []
        self._engine_io = threading.Lock()
        self._release_gen = 0
        self._engine_quiet = False

    def configure(
        self,
        device: int,
        cache_mb: int,
        fatbin_path: str,
        proxy_height: int = 270,
        proxy_vram_mb: int = 256,
    ) -> None:
        self._device = device
        self._cache_mb = cache_mb
        self._fatbin = fatbin_path
        self._proxy_height = proxy_height
        self._proxy_vram_mb = proxy_vram_mb
        if self._engine is None:
            self._engine = Engine(device, cache_mb, fatbin_path, proxy_height, proxy_vram_mb)

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("ScrubSession not configured")
        return self._engine

    @property
    def active(self) -> bool:
        return self._engine is not None

    @property
    def clip_info(self) -> dict | None:
        return self._clip_info

    @property
    def clip_path(self) -> str:
        return self._clip_path

    @property
    def last_request(self) -> int:
        return self._last_request

    @property
    def preview_gap(self) -> bool:
        """True when the playhead is not on a video block. Preview stays blank."""
        return self._preview_gap

    def add_blank_listener(self, fn: BlankFn) -> None:
        self._blank_listeners.append(fn)

    def remove_blank_listener(self, fn: BlankFn) -> None:
        try:
            self._blank_listeners.remove(fn)
        except ValueError:
            pass

    def blank_preview_now(self) -> None:
        """Drop the GPU image on the UI thread. Does not free decoder memory."""
        self._preview_gap = True
        self._play_dir = 0
        self._arrow_key_down = 0
        for fn in list(self._blank_listeners):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                carb.log_warn(f"[v1d.ngn.session] blank preview: {exc}")

    def release_media_async(self, paths: list[str], after_close: AfterCloseFn | None = None) -> None:
        """Clear the session view of the clip. Do not free the presented GPU frame.

        engine.close() cuda-frees the buffer Preview imported into Vulkan and the
        driver resets the device. The decoder stays resident until the next open.
        """
        self._preview_gap = True
        self._play_dir = 0
        self._arrow_key_down = 0
        self.blank_preview_now()
        try:
            self._audio_close()
        except Exception:  # noqa: BLE001
            pass
        engine = self._engine
        if engine is not None:
            try:
                engine.set_playback(False)
                # Scrubbing pauses the proxy builder so it does not rewrite the cache.
                engine.set_scrubbing(True)
            except Exception as exc:  # noqa: BLE001
                carb.log_warn(f"[v1d.ngn.session] pause before release: {exc}")
        self.clear_timeline()
        self._clip_info = None
        self._clip_path = ""
        self._last_request = 0
        self._preview_gap = True
        self._out_w = 0
        self._out_h = 0
        self._play_dir = 0
        self._last_status = "New project"
        self._engine_quiet = True
        carb.log_info("[v1d.ngn.session] new project: tracks cleared, GPU frame kept")
        if after_close is not None:
            try:
                after_close(list(paths))
            except Exception as exc:  # noqa: BLE001
                carb.log_warn(f"[v1d.ngn.session] proxy cache: {exc}")

    def set_preview_gap(self, gap: bool) -> None:
        """Blank the preview. Does not decode. Stops play so a held frame cannot return."""
        self._preview_gap = bool(gap)
        if not gap or (self._play_dir == 0 and self._arrow_key_down == 0):
            return
        self._play_dir = 0
        self._arrow_key_down = 0
        self._audio_pause()
        if self._engine is not None:
            self._engine.set_playback(False)
            self._engine.set_scrubbing(False)

    @property
    def play_dir(self) -> int:
        return self._play_dir

    @property
    def arrow_key_down(self) -> int:
        return self._arrow_key_down

    def add_frame_listener(self, fn: FrameFn) -> None:
        self._frame_listeners.append(fn)

    def remove_frame_listener(self, fn: FrameFn) -> None:
        try:
            self._frame_listeners.remove(fn)
        except ValueError:
            pass

    def add_sequence_listener(self, fn: SequenceFn) -> None:
        self._sequence_listeners.append(fn)

    def remove_sequence_listener(self, fn: SequenceFn) -> None:
        try:
            self._sequence_listeners.remove(fn)
        except ValueError:
            pass

    @property
    def timeline_mode(self) -> bool:
        return self._timeline_mode

    def add_clip_path_listener(self, fn: ClipPathFn) -> None:
        self._clip_path_listeners.append(fn)

    def remove_clip_path_listener(self, fn: ClipPathFn) -> None:
        try:
            self._clip_path_listeners.remove(fn)
        except ValueError:
            pass

    def clear_listeners(self) -> None:
        self._frame_listeners.clear()
        self._sequence_listeners.clear()
        self._clip_path_listeners.clear()
        self._listener_fail_logged.clear()

    def _emit_to_listeners(self, kind: str, listeners: list[T], *args) -> None:
        dead: list[T] = []
        for fn in listeners:
            try:
                fn(*args)
            except Exception as exc:  # noqa: BLE001
                key = id(fn)
                if key not in self._listener_fail_logged:
                    self._listener_fail_logged.add(key)
                    carb.log_warn(f"[v1d.ngn.session] {kind} listener: {exc}")
                dead.append(fn)
        for fn in dead:
            try:
                listeners.remove(fn)
            except ValueError:
                pass

    def _emit_clip_path(self, path: str) -> None:
        self._emit_to_listeners("clip_path", self._clip_path_listeners, path)

    def _emit_frame(self, frame: int) -> None:
        self._emit_to_listeners("frame", self._frame_listeners, frame)

    def _emit_sequence(self, seq: int) -> None:
        self._emit_to_listeners("sequence", self._sequence_listeners, int(seq))

    def configure_timeline(
        self,
        seq_lo: int,
        seq_hi: int,
        source_at_sequence: SourceAtSequenceFn,
        media_at_sequence: MediaAtSequenceFn | None = None,
    ) -> None:
        self._timeline_mode = True
        self._timeline_seq_lo = max(0, int(seq_lo))
        self._timeline_seq_hi = max(self._timeline_seq_lo, int(seq_hi))
        self._timeline_source_at = source_at_sequence
        self._timeline_media_at = media_at_sequence

    def clear_timeline(self) -> None:
        self._timeline_mode = False
        self._timeline_source_at = None
        self._timeline_media_at = None
        self._last_emitted_src = None

    def frame_max(self) -> int:
        if not self._clip_info:
            return 0
        return max(0, int(self._clip_info["frames"]) - 1)

    def playback_fps(self) -> float:
        if not self._clip_info:
            return 30.0
        den = max(1, int(self._clip_info["fps_den"]))
        return float(self._clip_info["fps_num"]) / den

    def _open_engine_clip(self, path: str) -> dict:
        path = path.strip()
        with self._engine_io:
            self._release_gen += 1
            self._engine_quiet = False
            self.engine.set_playback(False)
            self.engine.set_scrubbing(False)
            info = self.engine.open_clip(path)
        import pathlib

        self._clip_path = str(pathlib.Path(path).resolve())
        self._clip_info = info
        n = int(info["frames"])
        src_w = int(info["width"])
        src_h = int(info["height"])
        if self._out_w <= 0 or self._out_h <= 0:
            self._out_w = _even_down(min(960, src_w))
            self._out_h = _even_down(min(540, src_h))
        self.engine.set_output_size(self._out_w, self._out_h)
        self._last_status = f"{self._clip_path} — {n} frames"
        return info

    def ensure_media_path(self, path: str) -> None:
        if not path or not path.strip():
            return
        import pathlib

        resolved = str(pathlib.Path(path).resolve())
        if resolved == self._clip_path and self._clip_info:
            return
        self._open_engine_clip(resolved)
        if self._timeline_mode:
            self._audio_open(self._clip_path)

    def open_clip(self, path: str, *, reset_timeline: bool = True) -> dict:
        info = self._open_engine_clip(path)
        n = int(info["frames"])
        self._last_request = 0
        self._preview_gap = False
        if reset_timeline:
            self.clear_timeline()
        self._play_dir = 0
        self._play_pos = 0.0
        self._arrow_key_down = 0
        self._reset_arrow_gesture()
        self.engine.request_frame(0)
        self._emit_frame(0)
        self._emit_clip_path(self._clip_path)
        self._audio_open(self._clip_path)
        return info

    def open_fixture(self, fixture_name: str) -> dict:
        path = fixture_path(fixture_name)
        if not path.is_file():
            raise FileNotFoundError(f"fixture not found: {path}")
        return self.open_clip(str(path))

    def set_scrubbing(self, scrubbing: bool) -> None:
        self.engine.set_scrubbing(scrubbing)

    def request_frame(self, frame: int) -> None:
        frame = max(0, min(self.frame_max(), int(frame)))
        self._last_request = frame
        self.engine.request_frame(frame)
        self._emit_frame(frame)

    def seek_to_frame(self, frame: int) -> None:
        if not self._clip_info:
            return
        self._play_dir = 0
        self.engine.set_playback(False)
        self.engine.set_scrubbing(False)
        self._audio_pause()
        self.request_frame(frame)

    def step_frame(self, direction: int) -> None:
        if not self._clip_info:
            return
        self._audio_pause()
        if self._play_dir != 0:
            self.transport_stop()
        if not self.on_arrow_pressed(direction, self._last_request):
            return
        self.on_arrow_released(direction)

    def transport_play(
        self,
        direction: int,
        now: float | None = None,
        *,
        origin_sequence: int | None = None,
    ) -> None:
        if not self._clip_info:
            return
        if self._play_dir == direction:
            self.transport_stop()
            return
        if now is None:
            now = time.perf_counter()
        self._arrow_key_down = 0
        self._arrow_t_down = 0.0
        self._arrow_hold_promoted = False
        self._play_dir = direction
        if self._timeline_mode and origin_sequence is not None:
            origin = max(self._timeline_seq_lo, min(self._timeline_seq_hi, int(origin_sequence)))
            self._arrow_play_origin = origin
            self._play_emit_frame = origin
        else:
            self._arrow_play_origin = self._last_request
            self._play_emit_frame = self._last_request
        self._arrow_play_t0 = now
        self.engine.set_playback(True)
        self.engine.set_scrubbing(True)
        if self._timeline_mode:
            src = self._source_at_sequence(self._arrow_play_origin)
            if src is not None and direction > 0:
                self._audio_play_at(src / self.playback_fps())
            else:
                self._audio_pause()
        elif direction > 0:
            self._audio_play_at(self._last_request / self.playback_fps())
        else:
            self._audio_pause()

    def transport_stop(self) -> None:
        if not self._clip_info:
            return
        idx = self._last_request
        self._play_dir = 0
        self._arrow_key_down = 0
        self.engine.set_playback(False)
        self.engine.set_scrubbing(False)
        self._audio_pause()
        if not self._preview_gap:
            self.request_frame(idx)

    def _reset_arrow_gesture(self) -> None:
        self._arrow_key_down = 0
        self._arrow_t_down = 0.0
        self._arrow_stepped_frame = 0
        self._arrow_play_origin = 0
        self._arrow_play_t0 = 0.0
        self._play_emit_frame = 0
        self._arrow_hold_promoted = False
        self._play_dir = 0
        self._play_pos = 0.0

    def on_slider_begin(self) -> None:
        self._reset_arrow_gesture()
        self.engine.set_playback(False)
        self.engine.set_scrubbing(True)
        self._audio_pause()

    def on_slider_change(self, frame: int) -> None:
        self.request_frame(frame)

    def on_slider_end(self, frame: int) -> None:
        self.engine.set_scrubbing(False)
        self.request_frame(frame)

    def on_arrow_pressed(self, direction: int, current_frame: int, now: float | None = None) -> bool:
        """Tap step with scrub on (proxy/snap); hold promotes in tick_playback."""
        if not self._clip_info:
            return False
        if self._arrow_key_down == direction:
            return True
        if self._arrow_key_down != 0 or self._play_dir != 0:
            self._play_dir = 0
            self._arrow_key_down = 0
            self.engine.set_playback(False)
            self.engine.set_scrubbing(False)
        frame_max = self.frame_max()
        cur = max(0, min(frame_max, int(current_frame)))
        if direction > 0 and cur >= frame_max:
            return False
        if direction < 0 and cur <= 0:
            return False
        stepped = cur + direction
        if now is None:
            now = time.perf_counter()
        self._arrow_key_down = direction
        self._arrow_t_down = now
        self._arrow_stepped_frame = stepped
        self._play_emit_frame = stepped
        self._arrow_hold_promoted = False
        self._play_dir = 0
        self.engine.set_playback(False)
        self.engine.set_scrubbing(True)
        self._audio_pause()
        self.request_frame(stepped)
        return True

    def on_arrow_sequence_arm(self, direction: int, stepped_sequence: int, now: float | None = None) -> bool:
        """Arm arrow-hold shuttle in sequence frame space (tlv seeks before calling)."""
        if not self._clip_info or not self._timeline_mode:
            return False
        if self._arrow_key_down == direction:
            return True
        if self._arrow_key_down != 0 or self._play_dir != 0:
            self._play_dir = 0
            self._arrow_key_down = 0
            self.engine.set_playback(False)
            self.engine.set_scrubbing(False)
        seq = max(self._timeline_seq_lo, min(self._timeline_seq_hi, int(stepped_sequence)))
        if direction > 0 and seq >= self._timeline_seq_hi:
            return False
        if direction < 0 and seq <= self._timeline_seq_lo:
            return False
        if now is None:
            now = time.perf_counter()
        self._arrow_key_down = direction
        self._arrow_t_down = now
        self._arrow_stepped_frame = seq
        self._play_emit_frame = seq
        self._arrow_hold_promoted = False
        self._play_dir = 0
        self.engine.set_playback(False)
        self.engine.set_scrubbing(True)
        self._audio_pause()
        return True

    def on_arrow_released(self, direction: int) -> None:
        if self._arrow_key_down != direction and self._play_dir != direction:
            return
        idx = self._last_request
        self._reset_arrow_gesture()
        self.seek_to_frame(idx)

    def _emit_play_range(self, start: int, target: int, step: int) -> None:
        if step > 0 and target >= start:
            frames = range(start + 1, target + 1)
        elif step < 0 and target <= start:
            frames = range(start - 1, target - 1, step)
        else:
            return
        # Motion uses proxy when ready (same as hold-arrow). Button play keeps
        # playback on so a missing cache still sequential-decodes; stop/release
        # turns scrubbing off and settles exact.
        playing = self._arrow_key_down == 0
        self.engine.set_playback(playing)
        self.engine.set_scrubbing(True)
        for frame in frames:
            self._last_request = frame
            self.engine.request_frame(frame)
            self._emit_frame(frame)
        self._play_emit_frame = target

    def _source_at_sequence(self, seq: int) -> int | None:
        if self._timeline_source_at is None:
            return None
        try:
            return self._timeline_source_at(int(seq))
        except Exception:  # noqa: BLE001
            return None

    def _audio_timeline_step(self, src: int, direction: int) -> None:
        prev = self._last_emitted_src
        self._last_emitted_src = int(src)
        if prev is not None and abs(int(src) - int(prev)) != 1:
            if direction > 0:
                self._audio_play_at(src / self.playback_fps())
            else:
                self._audio_pause()
        elif prev is None and direction > 0:
            self._audio_play_at(src / self.playback_fps())

    def _maybe_switch_timeline_media(self, seq: int) -> None:
        if self._timeline_media_at is None:
            return
        try:
            path = self._timeline_media_at(int(seq))
        except Exception:  # noqa: BLE001
            return
        if path:
            self.ensure_media_path(path)

    def _emit_sequence_step(self, seq: int, direction: int, playing: bool) -> None:
        self._maybe_switch_timeline_media(seq)
        src = self._source_at_sequence(seq)
        self._emit_sequence(seq)
        self.engine.set_playback(playing)
        self.engine.set_scrubbing(True)
        if src is None:
            self._preview_gap = True
            self._audio_pause()
            return
        self._preview_gap = False
        self._last_request = int(src)
        self.engine.request_frame(int(src))
        self._emit_frame(int(src))
        self._audio_timeline_step(int(src), direction)

    def _emit_timeline_play_range(self, start: int, target: int, step: int) -> None:
        if step > 0 and target >= start:
            frames = range(start + 1, target + 1)
        elif step < 0 and target <= start:
            frames = range(start - 1, target - 1, step)
        else:
            return
        playing = self._arrow_key_down == 0
        for seq in frames:
            self._emit_sequence_step(seq, step, playing)
        self._play_emit_frame = target

    def _tick_timeline_playback(self, now: float) -> None:
        if not self._timeline_mode or self._timeline_source_at is None:
            return

        if self._play_dir == 0 and self._arrow_key_down != 0 and not self._arrow_hold_promoted:
            if now - self._arrow_t_down < ARROW_HOLD_S:
                return
            self._arrow_hold_promoted = True
            self._play_dir = self._arrow_key_down
            self._arrow_play_origin = self._arrow_stepped_frame
            self._arrow_play_t0 = self._arrow_t_down + ARROW_HOLD_S
            self._play_emit_frame = self._arrow_stepped_frame
            self.engine.set_playback(False)
            self.engine.set_scrubbing(True)

        if self._play_dir == 0:
            return

        step = self._play_dir
        fps = self.playback_fps()
        elapsed = max(0.0, now - self._arrow_play_t0)
        origin = self._arrow_play_origin
        delta = int(elapsed * fps)
        seq_hi = self._timeline_seq_hi
        seq_lo = self._timeline_seq_lo
        if step > 0:
            target = min(seq_hi, origin + delta)
            hit_end = target >= seq_hi
        else:
            target = max(seq_lo, origin - delta)
            hit_end = target <= seq_lo

        if target != self._play_emit_frame and step != 0:
            self._emit_timeline_play_range(self._play_emit_frame, target, step)
        if hit_end:
            self._play_dir = 0

    def tick_playback(
        self,
        get_current_frame: Callable[[], int] | None = None,
        now: float | None = None,
    ) -> None:
        if not self._clip_info:
            return
        if self._arrow_key_down == 0 and self._play_dir == 0:
            return
        if now is None:
            now = time.perf_counter()

        if self._timeline_mode:
            self._tick_timeline_playback(now)
            return

        if self._play_dir == 0 and self._arrow_key_down != 0 and not self._arrow_hold_promoted:
            if now - self._arrow_t_down < ARROW_HOLD_S:
                return
            self._arrow_hold_promoted = True
            self._play_dir = self._arrow_key_down
            self._arrow_play_origin = self._arrow_stepped_frame
            self._arrow_play_t0 = self._arrow_t_down + ARROW_HOLD_S
            self._play_emit_frame = self._arrow_stepped_frame
            self.engine.set_playback(False)
            self.engine.set_scrubbing(True)

        if self._play_dir == 0:
            return

        step = self._play_dir
        frame_max = self.frame_max()
        fps = self.playback_fps()
        elapsed = max(0.0, now - self._arrow_play_t0)
        origin = self._arrow_play_origin
        delta = int(elapsed * fps)
        if step > 0:
            target = min(frame_max, origin + delta)
            hit_end = target >= frame_max
        else:
            target = max(0, origin - delta)
            hit_end = target <= 0

        if target != self._play_emit_frame and step != 0:
            self._emit_play_range(self._play_emit_frame, target, step)
        if hit_end:
            self._play_dir = 0

    def refresh_status_line(self, tier: str | None = None, latency_us: int | None = None, frame_idx: int | None = None) -> None:
        if not self._clip_info:
            return
        idx = frame_idx if frame_idx is not None else self._last_request
        tier_s = tier if tier is not None else "—"
        lat_s = f"{latency_us / 1000:.1f} ms" if latency_us is not None else "—"
        play = ""
        if self._play_dir == 1:
            play = " play▶"
        elif self._play_dir == -1:
            play = " play◀"
        now = time.perf_counter()
        if now - self._stats_t >= 0.25 or not self._stats_cache:
            self._stats_cache = self.engine.stats()
            self._stats_t = now
        st = self._stats_cache
        proxy = ""
        if not st.get("proxy_ready"):
            total = int(st.get("proxy_build_total") or 0)
            done = int(st.get("proxy_build_frame") or 0)
            if total > 0 and done < total:
                proxy = f" proxy {done}/{total}"
        self._last_status = (
            f"frame {idx}/{self._clip_info['frames'] - 1}{play} "
            f"tier={tier_s} lat={lat_s}{proxy}"
        )

    def latest_present(self) -> dict | None:
        """Stable preview-sized RGBA (updated each publish). Safe for v1d.ups."""
        if not self._clip_info or self._engine_quiet:
            return None
        return self.engine.latest_present()

    def copy_latest_rgba_to(self, dst_ptr: int, dst_stride: int) -> bool:
        return self.engine.copy_latest_rgba_to(dst_ptr, dst_stride)

    def poll_frame(self) -> dict | None:
        """Poll present ring (call from preview only)."""
        if not self._clip_info or self._engine_quiet:
            return None
        frame = self.engine.poll()
        if frame is None:
            self.refresh_status_line()
            return None
        self.refresh_status_line(frame["tier"], int(frame["latency_us"]), int(frame["frame"]))
        return frame

    @property
    def last_status(self) -> str:
        return self._last_status

    def shutdown(self) -> None:
        self._audio_close()
        self.clear_timeline()
        self.clear_listeners()
        if self._engine:
            self._engine.shutdown()
            self._engine = None
        self._clip_info = None
        ScrubSession._instance = None

    def _audio_open(self, path: str) -> None:
        audio = getattr(self, "_audio", None)
        if audio is None:
            return
        try:
            audio.open(path)
        except Exception as exc:  # noqa: BLE001
            carb.log_warn(f"[v1d.ngn.audio] open skipped: {exc}")

    def _audio_play_at(self, seconds: float) -> None:
        audio = getattr(self, "_audio", None)
        if audio is None:
            return
        try:
            audio.play_at(seconds)
        except Exception as exc:  # noqa: BLE001
            carb.log_warn(f"[v1d.ngn.audio] play skipped: {exc}")

    def _audio_pause(self) -> None:
        audio = getattr(self, "_audio", None)
        if audio is None:
            return
        try:
            audio.pause()
        except Exception as exc:  # noqa: BLE001
            carb.log_warn(f"[v1d.ngn.audio] pause skipped: {exc}")

    def _audio_close(self) -> None:
        audio = getattr(self, "_audio", None)
        if audio is None:
            return
        try:
            audio.close()
        except Exception as exc:  # noqa: BLE001
            carb.log_warn(f"[v1d.ngn.audio] close skipped: {exc}")
