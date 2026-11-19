# SPDX-License-Identifier: MIT
"""Registry so v1d.pv menus can call v1d.tl project actions without importing tl."""

from __future__ import annotations

from typing import Any, Callable

_hooks: dict[str, Callable[..., Any]] = {}


def register(name: str, fn: Callable[..., Any]) -> None:
    _hooks[name] = fn


def unregister(name: str) -> None:
    _hooks.pop(name, None)


def call(name: str, *args: Any, **kwargs: Any) -> Any:
    fn = _hooks.get(name)
    if fn is None:
        return None
    return fn(*args, **kwargs)