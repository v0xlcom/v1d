# SPDX-License-Identifier: MIT
"""C13: tools/v1d serve RPC (headless)."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
TOOLS = ROOT / "tools" / "v1d"
CLIP = ROOT / "tests" / "fixtures" / "h264_1080_gop2.mp4"
REL = ROOT / "_build/linux-x86_64/release"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REL}/exts/v1d.cor:{env.get('PYTHONPATH', '')}"
    env["LD_LIBRARY_PATH"] = f"{REL}/kit:{env.get('LD_LIBRARY_PATH', '')}"
    env["V1D_ROOT"] = str(ROOT)
    return env


@unittest.skipUnless(CLIP.is_file(), "fixture missing")
@unittest.skipUnless(REL.is_dir(), "build missing")
class TestHeadlessC13(unittest.TestCase):
    def setUp(self):
        from v1d.ngn.paths import serve_socket_path  # noqa: PLC0415

        self._sock = serve_socket_path()
        if self._sock.exists():
            self._sock.unlink()

    def tearDown(self):
        from v1d.ngn.paths import serve_socket_path  # noqa: PLC0415

        sock = serve_socket_path()
        if sock.exists():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
                    c.connect(str(sock))
                    c.sendall(b'{"method":"shutdown","args":{}}\n')
            except OSError:
                pass
            time.sleep(0.2)
            sock.unlink(missing_ok=True)

    def test_serve_open_scrub_status(self):
        py = REL / "kit/python/bin/python3"
        proc = subprocess.Popen(
            [str(py), "-m", "v1d.ngn.headless_serve"],
            env=_env(),
            cwd=str(ROOT),
        )
        for _ in range(40):
            if self._sock.exists():
                break
            time.sleep(0.1)
        self.assertTrue(self._sock.exists(), "serve socket")
        out = subprocess.check_output(
            [str(py), str(TOOLS), "open", str(CLIP)],
            env=_env(),
            text=True,
        )
        row = json.loads(out)
        self.assertTrue(row["ok"])
        out2 = subprocess.check_output([str(py), str(TOOLS), "scrub", "5"], env=_env(), text=True)
        self.assertTrue(json.loads(out2)["ok"])
        out3 = subprocess.check_output([str(py), str(TOOLS), "status"], env=_env(), text=True)
        st = json.loads(out3)["summary"]
        self.assertEqual(st["frame"], 5)
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
