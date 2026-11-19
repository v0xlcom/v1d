#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""S4: headless reverse hold simulation; prints JSON rows for docs/SPIKES.md."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REL = ROOT / "_build/linux-x86_64/release"
KIT_PY = REL / "kit/python/bin/python3"
if KIT_PY.is_file() and Path(sys.executable).resolve() != KIT_PY.resolve():
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = f"{REL}/kit:{env.get('LD_LIBRARY_PATH', '')}"
    env["PYTHONPATH"] = f"{REL}/exts/v1d.cor:{env.get('PYTHONPATH', '')}"
    env.setdefault("V1D_ROOT", str(ROOT))
    os.execve(str(KIT_PY), [str(KIT_PY), str(Path(__file__).resolve())], env)

sys.path.insert(0, str(REL / "exts/v1d.cor"))

from v1d.ngn import Engine  # noqa: E402
from v1d.ngn.paths import default_fatbin  # noqa: E402
from v1d.ngn.fixtures import S4_FIXTURE_CHOICES, fixture_path  # noqa: E402


def _even_down(v: int) -> int:
    return v & ~1 if v > 0 else 0


def _percentile(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    s = sorted(samples)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _wait_poll(engine: Engine, timeout_s: float = 3.0) -> dict | None:
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        frame = engine.poll()
        if frame is not None:
            return frame
        time.sleep(0.002)
    return None


def bench_fixture(name: str, duration_s: float = 3.0) -> dict:
    path = fixture_path(name)
    if not path.is_file():
        return {"fixture": name, "error": f"missing {path}"}
    fatbin = str(default_fatbin())
    engine = Engine(0, 0, fatbin)
    try:
        info = engine.open_clip(str(path))
        n = int(info["frames"])
        frame_max = max(0, n - 1)
        out_w = _even_down(min(960, int(info["width"])))
        out_h = _even_down(min(540, int(info["height"])))
        engine.set_output_size(out_w, out_h)
        den = max(1, int(info["fps_den"]))
        fps = float(info["fps_num"]) / den
        frame_budget_s = 1.0 / fps

        engine.set_scrubbing(False)
        engine.request_frame(frame_max)
        if _wait_poll(engine, 5.0) is None:
            return {"fixture": name, "error": "timeout seeking to end"}

        engine.set_scrubbing(True)
        latencies_us: list[int] = []
        tiers: list[str] = []
        advances = 0
        steps = max(1, int(duration_s * fps))
        t0 = time.perf_counter()
        for step in range(steps):
            target = max(0, frame_max - step)
            engine.request_frame(target)
            step_t0 = time.perf_counter()
            frame = _wait_poll(engine, min(3.0, frame_budget_s * 8))
            if frame is None:
                continue
            advances += 1
            latencies_us.append(int(frame["latency_us"]))
            tiers.append(str(frame["tier"]))
            elapsed = time.perf_counter() - step_t0
            sleep_s = frame_budget_s - elapsed
            if sleep_s > 0:
                time.sleep(sleep_s)
            if time.perf_counter() - t0 >= duration_s:
                break

        tier_mode = max(set(tiers), key=tiers.count) if tiers else "?"
        lat_ms = [x / 1000.0 for x in latencies_us]
        keeps_fps = advances >= max(1, int(steps * 0.6))
        return {
            "fixture": name,
            "tier": tier_mode,
            "latency_p50_ms": round(_percentile(lat_ms, 0.50), 2),
            "latency_p95_ms": round(_percentile(lat_ms, 0.95), 2),
            "keeps_fps": keeps_fps,
            "samples": len(latencies_us),
            "advances": advances,
            "steps": steps,
        }
    finally:
        engine.shutdown()


def main() -> int:
    rows = []
    for name, _label in S4_FIXTURE_CHOICES:
        rows.append(bench_fixture(name))
    print(json.dumps({"s4": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
