# Progress — `v1d.ups` (PLAN_04)

Recorded numbers: [../../../docs/SPIKES.md](../../../docs/SPIKES.md) (section **U**).

| Gate | Status | Notes |
|------|--------|-------|
| **U0** | Pass | `v1d_ups/build.sh`; `fake`, `realesrgan`, `realcugan` on 64×64 PNG |
| **U1** | Manual | Six combo labels; idle without clip — [GUI §5.1](../../../docs/GUI_TEST_PLAN.md) |
| **U2** | Manual | GOP 2, Real-ESRGAN, wipe + scrub — [GUI §5.2–5.3](../../../docs/GUI_TEST_PLAN.md) |
| **U3** | Recorded fail (optional) | `seedvr2`, `flashvsr`, `video2x`, `rve` — no venv/helpers yet |

Implementation in tree: `extension.py`, `wipe.py`, `run.py`, `png_io.py`; `v1d.cor` adds `latest` + `cuda_write_rgba`.

**Pause:** close U1–U2 in SPIKES after Kit verify; then archive or waive [PLAN_04_UPS.md](PLAN_04_UPS.md).
