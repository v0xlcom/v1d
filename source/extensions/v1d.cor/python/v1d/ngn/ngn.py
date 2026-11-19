# SPDX-License-Identifier: MIT
"""Python façade over _scrub engine handles."""

from __future__ import annotations

from . import _scrub


class Engine:
    def __init__(
        self,
        cuda_device: int = 0,
        cache_mb: int = 0,
        fatbin_path: str = "",
        proxy_height: int = 270,
        proxy_vram_mb: int = 256,
    ):
        self._handle = int(
            _scrub._engine_new(cuda_device, cache_mb, fatbin_path, proxy_height, proxy_vram_mb)
        )

    def open_clip(self, path: str) -> dict:
        return _scrub._engine_open_clip(self._handle, path)

    def set_output_size(self, width: int, height: int) -> None:
        _scrub._engine_set_output_size(self._handle, width, height)

    def set_scrubbing(self, scrubbing: bool) -> None:
        _scrub._engine_set_scrubbing(self._handle, scrubbing)

    def set_playback(self, playback: bool) -> None:
        _scrub._engine_set_playback(self._handle, playback)

    def request_frame(self, presentation_index: int) -> None:
        _scrub._engine_request_frame(self._handle, presentation_index)

    def poll(self):
        return _scrub._engine_poll(self._handle)

    def latest_present(self):
        return _scrub._engine_latest_present(self._handle)

    def copy_latest_rgba_to(self, dst_ptr: int, dst_stride: int) -> bool:
        return bool(_scrub._engine_copy_latest_rgba(self._handle, int(dst_ptr), int(dst_stride)))

    def stats(self) -> dict:
        return _scrub._engine_stats(self._handle)

    def debug_read_rgba(self, ptr: int) -> bytes:
        return _scrub._engine_debug_read_rgba(self._handle, int(ptr))

    def close(self) -> None:
        if self._handle:
            _scrub._engine_close(self._handle)

    def shutdown(self) -> None:
        if not self._handle:
            return
        _scrub._engine_shutdown(self._handle)
        _scrub._engine_delete(self._handle)
        self._handle = 0
