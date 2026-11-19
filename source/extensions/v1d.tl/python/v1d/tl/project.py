# SPDX-License-Identifier: MIT
"""`.v1d` project file I/O (composition only; media stays on disk)."""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
from typing import Any


def media_rel_path(media_path: str, base_dir: pathlib.Path) -> str:
    try:
        return str(pathlib.Path(media_path).resolve().relative_to(base_dir.resolve()))
    except ValueError:
        return ""


def save_project(path: str | pathlib.Path, state: dict[str, Any]) -> None:
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".v1d-", suffix=".tmp", dir=str(target.parent))
    os.close(fd)
    tmp = pathlib.Path(tmp_name)
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def load_project(path: str | pathlib.Path) -> tuple[dict[str, Any], pathlib.Path]:
    target = pathlib.Path(path).resolve()
    with target.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data, target.parent