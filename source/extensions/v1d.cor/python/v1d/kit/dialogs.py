# SPDX-License-Identifier: MIT
"""File dialogs — zenity today; Kit file_importer/exporter when wired."""

from __future__ import annotations

import pathlib
import subprocess
from typing import Literal


def _zenity(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["zenity", *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    return out if out else None


def pick_open_v1d() -> str | None:
    return _zenity(
        [
            "--file-selection",
            "--title=Open .v1d",
            "--file-filter=v1d project | *.v1d",
            "--file-filter=All files | *",
        ]
    )


def pick_save_v1d(default_name: str = "untitled.v1d") -> str | None:
    return _zenity(
        [
            "--file-selection",
            "--save",
            "--confirm-overwrite",
            f"--filename={default_name}",
            "--title=Save .v1d",
            "--file-filter=v1d project | *.v1d",
        ]
    )


def pick_open_video() -> str | None:
    return _zenity(
        [
            "--file-selection",
            "--title=Open video",
            "--file-filter=Video | *.mp4 *.mov *.m4v",
            "--file-filter=All files | *",
        ]
    )


def pick_folder(title: str = "Output folder") -> str | None:
    return _zenity(["--file-selection", "--directory", f"--title={title}"])


def ask_save_discard() -> Literal["save", "discard", "cancel"]:
    text = _zenity(
        [
            "--question",
            "--title=Unsaved project",
            "--text=Save changes before continuing?",
            "--ok-label=Save",
            "--cancel-label=Cancel",
            "--extra-button=Discard",
        ]
    )
    if text is None:
        return "cancel"
    if text.lower() == "discard":
        return "discard"
    return "save"