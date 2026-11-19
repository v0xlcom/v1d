# SPDX-License-Identifier: MIT
"""Headless-importable scrub package (no omni imports)."""

from ._scrub import __version__  # noqa: F401
from .ngn import Engine

__all__ = ["__version__", "Engine"]
