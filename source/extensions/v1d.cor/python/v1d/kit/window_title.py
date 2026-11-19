# SPDX-License-Identifier: MIT

from __future__ import annotations

import ctypes
import sys

import carb

APP_TITLE = "v1d"
# Panel match key. Kit's default class is "v1d <version>" ("v1d 0.1.0").
# Cinnamon turns that into v1d-0.1.0.desktop, misses v1d.desktop, and shows
# application-default-icon (a gear). 5urf is launched as the desktop app, so
# its window stays tied to 5urf.desktop. v1d's launcher is a terminal, so the
# Kit window has to carry this class itself.
_WM_CLASS = b"v1d"


def apply_window_title() -> None:
    settings = carb.settings.get_settings()
    settings.set("/app/window/title", APP_TITLE)
    try:
        from omni.kit.window.title import get_main_window_title

        wt = get_main_window_title()
        if wt:
            wt.set_app_name("v1d")
            wt.set_app_version("")
            wt.set_title("")
    except ImportError:
        pass
    _apply_wm_class()


def _native_address(handle) -> int:
    if isinstance(handle, int):
        return handle
    if handle is None:
        raise RuntimeError("missing native handle")
    get_name = ctypes.pythonapi.PyCapsule_GetName
    get_name.restype = ctypes.c_char_p
    get_name.argtypes = [ctypes.py_object]
    get_ptr = ctypes.pythonapi.PyCapsule_GetPointer
    get_ptr.restype = ctypes.c_void_p
    get_ptr.argtypes = [ctypes.py_object, ctypes.c_char_p]
    err_occurred = ctypes.pythonapi.PyErr_Occurred
    err_occurred.restype = ctypes.c_void_p
    name = get_name(handle)
    if err_occurred():
        ctypes.pythonapi.PyErr_Clear()
        name = None
    ptr = get_ptr(handle, name)
    if not ptr:
        ctypes.pythonapi.PyErr_Clear()
        raise RuntimeError("empty native handle")
    return int(ptr)


class _XClassHint(ctypes.Structure):
    _fields_ = [("res_name", ctypes.c_char_p), ("res_class", ctypes.c_char_p)]


def _apply_wm_class() -> None:
    if not sys.platform.startswith("linux"):
        return
    try:
        import carb.windowing
        import omni.appwindow

        app = omni.appwindow.get_default_app_window()
        native = app.get_window() if app is not None else None
        if native is None:
            return
        windowing = carb.windowing.acquire_windowing_interface()
        display = _native_address(windowing.get_native_display(native))
        xid = _native_address(windowing.get_native_window(native))
        if _set_x11_class(display, xid):
            carb.log_info("[v1d] WM_CLASS set to v1d")
    except Exception as exc:
        carb.log_warn(f"[v1d] WM_CLASS not set: {exc}")


def _set_x11_class(display: int, xid: int) -> bool:
    x11 = ctypes.CDLL("libX11.so.6")
    x11.XSetClassHint.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_XClassHint)]
    x11.XSetClassHint.restype = ctypes.c_int
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XFlush.restype = ctypes.c_int
    name = ctypes.create_string_buffer(_WM_CLASS)
    klass = ctypes.create_string_buffer(_WM_CLASS)
    hint = _XClassHint(ctypes.cast(name, ctypes.c_char_p), ctypes.cast(klass, ctypes.c_char_p))
    status = x11.XSetClassHint(display, ctypes.c_ulong(xid), ctypes.byref(hint))
    x11.XFlush(display)
    return status != 0
