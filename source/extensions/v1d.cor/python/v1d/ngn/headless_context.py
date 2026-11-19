# SPDX-License-Identifier: MIT
"""Single-process engine state for tools/v1d serve (D7)."""

from __future__ import annotations

import pathlib
import time
from typing import Any

from v1d.ngn.ngn import Engine
from v1d.ngn.paths import default_fatbin
from v1d.ngn.fixtures import fixture_path


def _even_down(v: int) -> int:
    return v & ~1 if v > 0 else 0


class HeadlessContext:
    def __init__(
        self,
        cuda_device: int = 0,
        cache_mb: int = 0,
        fatbin_path: str | pathlib.Path | None = None,
    ) -> None:
        fb = str(fatbin_path or default_fatbin())
        self._engine = Engine(cuda_device, cache_mb, fb)
        self._clip_path = ""
        self._clip_info: dict[str, Any] | None = None
        self._last_request = 0
        self._play_dir = 0
        self._play_pos = 0.0
        self._play_t_last = 0.0
        self._scrubbing = False
        self._last_tier = ""
        self._last_latency_us = 0

    def shutdown(self) -> None:
        self._engine.shutdown()

    def _frame_max(self) -> int:
        if not self._clip_info:
            return 0
        return max(0, int(self._clip_info["frames"]) - 1)

    def _playback_fps(self) -> float:
        if not self._clip_info:
            return 30.0
        den = max(1, int(self._clip_info["fps_den"]))
        return float(self._clip_info["fps_num"]) / den

    def open_path(self, path: str) -> dict[str, Any]:
        path = path.strip()
        info = self._engine.open_clip(path)
        self._clip_path = str(pathlib.Path(path).resolve())
        self._clip_info = info
        src_w = int(info["width"])
        src_h = int(info["height"])
        self._engine.set_output_size(_even_down(min(960, src_w)), _even_down(min(540, src_h)))
        self._last_request = 0
        self._play_dir = 0
        self._play_pos = 0.0
        self._scrubbing = False
        self._engine.request_frame(0)
        self._drain_poll()
        return {"path": self._clip_path, "clip": info}

    def open_fixture(self, name: str) -> dict[str, Any]:
        p = fixture_path(name)
        if not p.is_file():
            raise FileNotFoundError(f"missing {p}")
        return self.open_path(str(p))

    def reload_clip(self) -> dict[str, Any]:
        if not self._clip_path:
            raise RuntimeError("no clip open")
        return self.open_path(self._clip_path)

    def scrub_begin(self) -> None:
        self._scrubbing = True
        self._engine.set_scrubbing(True)

    def scrub_frame(self, frame: int) -> None:
        if not self._clip_info:
            raise RuntimeError("no clip open")
        frame = max(0, min(self._frame_max(), int(frame)))
        self._last_request = frame
        self._engine.request_frame(frame)

    def scrub_end(self, frame: int) -> None:
        self._scrubbing = False
        self._engine.set_scrubbing(False)
        self.scrub_frame(frame)

    def play_forward(self, for_ms: int | None = None) -> dict[str, Any]:
        return self._play_start(1, for_ms)

    def play_back(self, for_ms: int | None = None) -> dict[str, Any]:
        return self._play_start(-1, for_ms)

    def _play_start(self, direction: int, for_ms: int | None) -> dict[str, Any]:
        if not self._clip_info:
            raise RuntimeError("no clip open")
        frame_max = self._frame_max()
        cur = self._last_request
        if direction > 0 and cur >= frame_max:
            return {"playing": False, "reason": "at_end"}
        if direction < 0 and cur <= 0:
            return {"playing": False, "reason": "at_start"}
        self._play_dir = direction
        self._play_pos = float(cur)
        self._play_t_last = time.perf_counter()
        self._engine.set_scrubbing(True)
        if for_ms is not None and for_ms > 0:
            self.tick_playback(for_ms / 1000.0)
            self.play_stop()
        return {"playing": self._play_dir != 0, "frame": self._last_request}

    def play_stop(self) -> dict[str, Any]:
        if self._play_dir != 0:
            self._play_dir = 0
            self._engine.set_scrubbing(False)
            frame = max(0, min(self._frame_max(), int(round(self._play_pos))))
            self.scrub_end(frame)
        return {"frame": self._last_request, "tier": self._last_tier}

    def tick_playback(self, max_dt: float | None = None) -> None:
        if self._play_dir == 0 or not self._clip_info:
            return
        deadline = time.perf_counter() + max_dt if max_dt is not None else None
        while True:
            now = time.perf_counter()
            if deadline is not None and now >= deadline:
                break
            dt = now - self._play_t_last
            self._play_t_last = now
            if dt <= 0.0:
                if deadline is None:
                    break
                continue
            frame_max = self._frame_max()
            self._play_pos += self._play_dir * dt * self._playback_fps()
            if self._play_pos < 0.0:
                self._play_pos = 0.0
                self._play_dir = 0
                self._engine.set_scrubbing(False)
                self.scrub_frame(0)
                break
            if self._play_pos > float(frame_max):
                self._play_pos = float(frame_max)
                self._play_dir = 0
                self._engine.set_scrubbing(False)
                self.scrub_frame(frame_max)
                break
            frame = int(self._play_pos)
            if frame != self._last_request:
                self._engine.set_scrubbing(True)
                self._last_request = frame
                self._engine.request_frame(frame)
            self._drain_poll()
            if deadline is None:
                break

    def _drain_poll(self) -> None:
        for _ in range(32):
            frame = self._engine.poll()
            if frame is None:
                break
            self._last_tier = str(frame["tier"])
            self._last_latency_us = int(frame["latency_us"])

    def status(self) -> dict[str, Any]:
        st = self._engine.stats()
        out: dict[str, Any] = {
            "clip": self._clip_path,
            "frame": self._last_request,
            "frame_max": self._frame_max(),
            "tier": self._last_tier,
            "latency_ms": self._last_latency_us / 1000.0,
            "playing": self._play_dir,
            "stats": st,
        }
        if self._clip_info:
            den = max(1, int(self._clip_info["fps_den"]))
            fps = float(self._clip_info["fps_num"]) / den
            out["time_s"] = self._last_request / fps
            out["fps"] = fps
        return out

    def set_cuda_device(self, device: int) -> dict[str, Any]:
        raise RuntimeError("cuda-device cannot change while serve is running")

    def set_cache_mb(self, mb: int) -> dict[str, Any]:
        raise RuntimeError("cache-mb cannot change while serve is running")

    def set_output(self, width: int, height: int) -> dict[str, Any]:
        if not self._clip_info:
            raise RuntimeError("no clip open")
        self._engine.set_output_size(_even_down(int(width)), _even_down(int(height)))
        return {"width": width, "height": height}
