# Performance (v1d)

Primary measurements live in [SPIKES.md](SPIKES.md) (S1–S3, S2 upload gates). This file records C8 product gates once C4–C7 are green.

## Reference (RTX 2060, driver 610.57.04)

| Gate | Metric | Threshold | Source |
|------|--------|-----------|--------|
| S1 | 4K H.264 sequential decode | ≥ 60 fps | SPIKES S1 |
| S1 | Single-IDR decode | ≤ 30 ms | SPIKES S1 |
| S2 | `set_bytes_data_from_gpu` p95 @ 720p | ≤ 3 ms | SPIKES S2 |
| S2 | `set_bytes_data_from_gpu` p95 @ 4K | ≤ 8 ms | SPIKES S2 |
| S3 | `bound_cold` (4K long GOP) | ≈ 1165 ms | SPIKES S3 |
| C8 | Cache-hit publish p95 @ 1080p output | ≤ 4 ms | 0.56 ms |
| C8 | Cold seek p95 | ≤ `bound_cold` | 70.05 ms |
| C8 | Snap p95 | ≤ S1 single-IDR + 20 ms | 2.07 ms |
| C8 | `poll()` p95 | ≤ 50 µs | 0.4 µs |

## Reverse play (S4)

Hold **←** comparison table: see `_archive/PLAN_01_SCRUB.md` § Reverse playback. Record in SPIKES.md when `v1d.tl` / `v1d.pv` comparison shell exists.
