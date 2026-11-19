# SPDX-License-Identifier: MIT
"""Test fixture paths (Kit-free)."""

from __future__ import annotations

import pathlib

from v1d.ngn.paths import v1d_root

S4_FIXTURE_CHOICES: tuple[tuple[str, str], ...] = (
    ("h264_1080_intra", "Intra (GOP 1)"),
    ("h264_1080_gop2", "GOP 2"),
    ("h264_1080_g30_b2", "GOP 30"),
    ("h264_4k_g250_b2", "4K GOP 250"),
)


def fixture_path(name: str) -> pathlib.Path:
    stem = name.strip()
    if stem.endswith(".mp4"):
        stem = stem[:-4]
    return v1d_root() / "tests" / "fixtures" / f"{stem}.mp4"


def fixture_index_for_path(path: str) -> int | None:
    try:
        resolved = pathlib.Path(path).resolve()
    except OSError:
        return None
    for i, (fname, _) in enumerate(S4_FIXTURE_CHOICES):
        try:
            if fixture_path(fname).resolve() == resolved:
                return i
        except OSError:
            continue
    return None
