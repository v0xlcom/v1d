# SPDX-License-Identifier: MIT
"""Host CPU power profiles via powerprofilesctl (no root)."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence

# Menu label, powerprofilesctl id. "Powersave" is the daemon's power-saver profile.
PROFILES: tuple[tuple[str, str], ...] = (
    ("Performance", "performance"),
    ("Balanced", "balanced"),
    ("Powersave", "power-saver"),
)

Run = Callable[..., subprocess.CompletedProcess[str]]


def active_profile(run: Run = subprocess.run) -> str | None:
    """Return the active profile id, or None when the tool is missing or fails."""
    try:
        result = run(
            ["powerprofilesctl", "get"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    name = (result.stdout or "").strip()
    return name or None


def set_profile(profile_id: str, run: Run = subprocess.run) -> tuple[bool, str]:
    """Apply a profile id. Returns (ok, error message)."""
    known = {pid for _label, pid in PROFILES}
    if profile_id not in known:
        return False, f"unknown power profile: {profile_id}"
    try:
        result = run(
            ["powerprofilesctl", "set", profile_id],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False, "powerprofilesctl is not installed"
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "powerprofilesctl set failed").strip()
        return False, err
    return True, ""


def profile_ids() -> Sequence[str]:
    return tuple(pid for _label, pid in PROFILES)
