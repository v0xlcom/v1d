# SPDX-License-Identifier: MIT
"""Repo paths for headless tools (no Kit)."""

from __future__ import annotations

import os
import pathlib


def v1d_root() -> pathlib.Path:
    env = os.environ.get("V1D_ROOT", "").strip()
    if env:
        return pathlib.Path(env)
    here = pathlib.Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "scripts" / "spawn-v1d-gui-terminal.sh").is_file():
            return parent
    return pathlib.Path.cwd()


def default_fatbin() -> pathlib.Path:
    root = v1d_root()
    built = root / "_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/convert.fatbin"
    if built.is_file():
        return built
    return pathlib.Path(__file__).resolve().parent / "convert.fatbin"


def serve_socket_path() -> pathlib.Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or os.path.expanduser("~/.local/share/v1d")
    return pathlib.Path(base) / "v1d-serve.sock"


def serve_state_dir() -> pathlib.Path:
    d = pathlib.Path(os.path.expanduser("~/.local/share/v1d"))
    d.mkdir(parents=True, exist_ok=True)
    return d
