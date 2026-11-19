# SPDX-License-Identifier: MIT
"""Menu-bar Reload: spawn new Kit terminal and quit."""

from __future__ import annotations

import os
import pathlib
import subprocess
import threading

import carb
import omni.kit.app


def _v1d_root() -> pathlib.Path:
    env = os.environ.get("V1D_ROOT", "").strip()
    if env:
        return pathlib.Path(env)
    here = pathlib.Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "scripts" / "spawn-v1d-gui-terminal.sh").is_file():
            return parent
    return pathlib.Path.cwd()


def _spawn_v1d_restart(env: dict[str, str]) -> bool:
    root = _v1d_root()
    spawn = root / "scripts" / "spawn-v1d-gui-terminal.sh"
    if not spawn.is_file():
        carb.log_error(f"[v1d.pv] Reload: missing {spawn}")
        return False
    launch = root / "scripts" / "launch-v1d-terminal.sh"
    env = dict(env)
    env.setdefault("V1D_ROOT", str(root))
    env.setdefault("V1D_LAUNCH_SCRIPT", str(launch))
    env.setdefault("V1D_RELOAD_LOG_TERMINAL", "1")
    for key in (
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XAUTHORITY",
        "DBUS_SESSION_BUS_ADDRESS",
        "HOME",
        "XDG_RUNTIME_DIR",
        "XDG_CURRENT_DESKTOP",
        "DESKTOP_SESSION",
    ):
        if key in os.environ and key not in env:
            env[key] = os.environ[key]
    path = env.get("PATH", os.environ.get("PATH", ""))
    if "/usr/bin" not in path.split(":"):
        env["PATH"] = f"/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:{path}"
    try:
        proc = subprocess.Popen(
            ["/bin/bash", str(spawn)],
            env=env,
            cwd=str(root),
            start_new_session=True,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        carb.log_error(f"[v1d.pv] Reload spawn failed: {exc}")
        return False
    carb.log_info(f"[v1d.pv] Reload: spawn pid={proc.pid}")
    return True


async def _post_quit_after_reload() -> None:
    settings = carb.settings.get_settings()
    # Full teardown (fastShutdown=false) can hold the X11/GLFW pointer grab until exit — feels like a frozen cursor.
    settings.set_bool("/app/fastShutdown", True)
    for _ in range(4):
        await omni.kit.app.get_app().next_update_async()
    omni.kit.app.get_app().post_quit(0)


def request_reload(clip_path: str = "") -> bool:
    settings = carb.settings.get_settings()
    env = os.environ.copy()
    if clip_path.strip():
        env["V1D_CLIP"] = clip_path.strip()
    if not settings.get("/exts/v1d.pv/ui/reload_parallel_log_terminal"):
        env["V1D_RELOAD_LOG_TERMINAL"] = "0"

    root = _v1d_root()
    if not (root / "scripts" / "spawn-v1d-gui-terminal.sh").is_file():
        carb.log_error("[v1d.pv] Reload: spawn script missing")
        return False

    try:
        from v1d.pv.ui import workspace_layout  # noqa: PLC0415

        workspace_layout.save_workspace()
    except Exception as exc:  # noqa: BLE001
        carb.log_warn(f"[v1d.pv] Reload: workspace save skipped: {exc}")

    def _spawn_and_quit() -> None:
        if not _spawn_v1d_restart(env):
            return
        carb.log_info("[v1d.pv] Reload: new instance spawned; shutting down Kit…")
        import omni.kit.async_engine  # noqa: PLC0415

        omni.kit.async_engine.run_coroutine(_post_quit_after_reload())

    threading.Thread(target=_spawn_and_quit, name="v1d.reload", daemon=True).start()
    return True
