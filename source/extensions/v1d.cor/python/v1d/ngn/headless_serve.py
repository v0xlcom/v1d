# SPDX-License-Identifier: MIT
"""Unix-socket JSON RPC for tools/v1d (one line per request)."""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import threading
from typing import Any

from v1d.ngn.headless_context import HeadlessContext
from v1d.ngn.paths import serve_socket_path, serve_state_dir


class ServeError(Exception):
    pass


def _handle_request(ctx: HeadlessContext, req: dict[str, Any]) -> dict[str, Any]:
    method = str(req.get("method") or "").strip()
    args = req.get("args") if isinstance(req.get("args"), dict) else {}

    try:
        if method == "open":
            path = str(args.get("path") or "")
            if not path:
                raise ServeError("open requires path")
            summary = ctx.open_path(path)
            return {"ok": True, "summary": summary}
        if method == "reload":
            summary = ctx.reload_clip()
            return {"ok": True, "summary": summary}
        if method == "scrub":
            sub = str(args.get("sub") or "")
            if sub == "begin":
                ctx.scrub_begin()
                return {"ok": True, "summary": {"scrubbing": True}}
            if sub == "end":
                ctx.scrub_end(int(args.get("frame", ctx._last_request)))
                return {"ok": True, "summary": {"scrubbing": False, "frame": ctx._last_request}}
            frame = args.get("frame")
            if frame is None:
                raise ServeError("scrub requires frame")
            ctx.scrub_frame(int(frame))
            ctx._drain_poll()
            return {"ok": True, "summary": {"frame": ctx._last_request}}
        if method == "play":
            sub = str(args.get("sub") or "")
            for_ms = args.get("for_ms")
            ms = int(for_ms) if for_ms is not None else None
            if sub == "forward":
                summary = ctx.play_forward(ms)
            elif sub == "back":
                summary = ctx.play_back(ms)
            elif sub == "stop":
                summary = ctx.play_stop()
            elif sub == "tick":
                ctx.tick_playback()
                ctx._drain_poll()
                summary = {"frame": ctx._last_request}
            else:
                raise ServeError("play requires sub forward|back|stop|tick")
            return {"ok": True, "summary": summary}
        if method == "status":
            ctx._drain_poll()
            return {"ok": True, "summary": ctx.status()}
        if method == "set":
            sub = str(args.get("sub") or "")
            if sub == "cuda-device":
                ctx.set_cuda_device(int(args.get("n", 0)))
            if sub == "cache-mb":
                ctx.set_cache_mb(int(args.get("n", 0)))
            if sub == "output":
                summary = ctx.set_output(int(args["w"]), int(args["h"]))
                return {"ok": True, "summary": summary}
            raise ServeError("set requires sub cuda-device|cache-mb|output")
        if method == "fixture":
            sub = str(args.get("sub") or "")
            if sub == "set":
                name = str(args.get("name") or "")
                summary = ctx.open_fixture(name)
                return {"ok": True, "summary": summary}
            raise ServeError("fixture requires sub set")
        if method == "shutdown":
            return {"ok": True, "summary": {"shutdown": True}}
        raise ServeError(f"unknown method: {method}")
    except ServeError as exc:
        return {"ok": False, "summary": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "summary": str(exc)}


def _client_conn(sock_path: str, payload: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(sock_path)
        sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
        line = buf.split(b"\n", 1)[0]
        return json.loads(line.decode("utf-8"))


def rpc(method: str, **args: Any) -> dict[str, Any]:
    path = str(serve_socket_path())
    if not os.path.exists(path):
        raise FileNotFoundError(f"v1d serve not running (no socket at {path})")
    return _client_conn(path, {"method": method, "args": args})


def serve_main(cuda_device: int = 0, cache_mb: int = 0) -> int:
    sock_path = serve_socket_path()
    state_dir = serve_state_dir()
    pid_path = state_dir / "v1d-serve.pid"
    if sock_path.exists():
        try:
            sock_path.unlink()
        except OSError:
            pass

    ctx = HeadlessContext(cuda_device=cuda_device, cache_mb=cache_mb)
    stop = threading.Event()

    def _on_signal(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(4)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")

    try:
        while not stop.is_set():
            server.settimeout(0.5)
            try:
                conn, _ = server.accept()
            except TimeoutError:
                continue
            with conn:
                data = b""
                while b"\n" not in data:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                if not data:
                    continue
                line = data.split(b"\n", 1)[0]
                req = json.loads(line.decode("utf-8"))
                resp = _handle_request(ctx, req)
                if req.get("method") == "shutdown" and resp.get("ok"):
                    conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                    break
                try:
                    conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                except BrokenPipeError:
                    pass
    finally:
        ctx.shutdown()
        server.close()
        try:
            sock_path.unlink(missing_ok=True)
        except TypeError:
            if sock_path.exists():
                sock_path.unlink()
        pid_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    dev = int(os.environ.get("V1D_CUDA_DEVICE", "0"))
    cache = int(os.environ.get("V1D_CACHE_MB", "0"))
    raise SystemExit(serve_main(dev, cache))
