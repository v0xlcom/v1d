# SPDX-License-Identifier: MIT
"""Bootstrap ScrubSession from settings (no UI)."""

from __future__ import annotations

import carb
import omni.ext

from v1d.kit.square_menu import install_default_square_ticks
from v1d.ngn.paths import default_fatbin
from v1d.ngn.session import ScrubSession


class V1dCorExtension(omni.ext.IExt):
    def on_startup(self, ext_id: str) -> None:
        install_default_square_ticks()
        settings = carb.settings.get_settings()
        device = int(settings.get("/exts/v1d.cor/cuda_device") or 0)
        cache_mb = int(settings.get("/exts/v1d.cor/cache_vram_mb") or 0)
        proxy_height = int(settings.get("/exts/v1d.cor/proxy_height") or 270)
        proxy_vram_mb = int(settings.get("/exts/v1d.cor/proxy_vram_mb") or 256)
        fatbin = str(default_fatbin())
        session = ScrubSession.get()
        session.configure(device, cache_mb, fatbin, proxy_height, proxy_vram_mb)
        clip = str(settings.get("/exts/v1d.cor/clip") or "").strip()
        if clip:
            try:
                session.open_clip(clip)
            except Exception as exc:  # noqa: BLE001
                carb.log_error(f"[v1d.cor] open_clip failed: {exc}")

    def on_shutdown(self) -> None:
        try:
            ScrubSession.get().shutdown()
        except Exception:  # noqa: BLE001
            pass
