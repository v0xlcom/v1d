# Spike results (Phase 0)

Machine: GeForce RTX 2060 12 GiB, driver 610.57.04, Ubuntu 26.04.

## S0 — toolchain (PASS)

| Check | Result |
|-------|--------|
| `./repo.sh build -r` | Success |
| `_scrub` import | `__version__` = `0.0.1` |
| `convert.fatbin` | Present under `exts/v1d.cor/v1d/ngn/` |

## Task 2 — fixtures (done)

Seven clips in `tests/fixtures/` via `tools/gen_fixtures.py`. H.264 uses `-pix_fmt yuv420p`.

## S1 — NVDEC (`spikes/s1_nvdec.cpp`) — **PASS**

Build (dev only):

```bash
g++-15 -O3 -std=c++17 spikes/s1_nvdec.cpp -o spikes/s1_nvdec \
  -I/usr/include/ffnvcodec $(pkg-config --cflags --libs libavformat libavcodec libavutil) -ldl -pthread
```

Dynlink `cuvid` + libav demux/BSF (dev only). **Critical:** `pfnSequenceCallback` must return `ulNumDecodeSurfaces`, not `1` (boolean success). Returning `1` capped the parser at ~9 pictures.

| Clip | packets | decode_cb | display | sequential_fps | single-IDR ms (2nd key) |
|------|---------|-----------|---------|----------------|-------------------------|
| `h264_4k_g250_b2` | 600 | 600 | 600 | **225.24** | 26.99 |
| `h264_1080_g30_b2` | 600 | 600 | 600 | 834.99 | 17.23 |
| `hevc_4k_g120_b2` | 600 | 600 | 600 | 454.95 | 25.27 |

### GATE S1

| Criterion | Threshold | Result |
|-----------|-----------|--------|
| 4K H.264 sequential | ≥ 60 fps | **PASS** (225.24) |
| Single-IDR latency | ≤ 30 ms | **PASS** (26.99 ms) |

Steady-state in-process; warmup excluded (single timed pass after one optional internal parser create).

## S2 — display path (`v1d.pv` + `ByteImageProvider.set_bytes_data_from_gpu`) — **PASS**

Launch (built extension tree, not `source/extensions` on `--ext-folder`):

```bash
ROOT=_build/linux-x86_64/release
$ROOT/kit/kit source/apps/v1d.app.kit \
  --ext-folder $ROOT/exts --ext-folder $ROOT/extscache --portable-root $ROOT \
  --/exts/v1d.pv/s2_bench=true --/app/window/hideUi=true --no-window
```

App kit: `v1d.app.kit` (id `v1d.app`). Do not add a `v1d.scrub` extension. Populate `extscache` from `../v1d_ref/kit-app-template/_build/linux-x86_64/release/extscache` when empty.

400 samples per resolution after 30-frame warmup; CUDA fill kernel then GPU upload timing. `cuMemGetInfo` via dynlink fails under Kit (logged, non-fatal); alloc/upload still work on primary context.

| Resolution | p50 ms | p95 ms |
|------------|--------|--------|
| 1280×720 | 0.023 | 0.045 |
| 3840×2160 | 0.025 | 0.046 |

p95_4k / p95_720 ratio ≈ **1.03** (host hop would be ~9× pixels).

### GATE S2

| Criterion | Threshold | Result |
|-----------|-----------|--------|
| 720p upload p95 | ≤ 3 ms | **PASS** (0.045) |
| 4K upload p95 | ≤ 8 ms | **PASS** (0.046) |

**hold_polls:** keep default **2** (gate margin is large; immediate reuse second upload logged ~same order as first).

Log: under `_build/linux-x86_64/release/logs/Kit/v1d.app/0.1/` (see `[v1d.pv S2]` lines in run output).

## S3 — cold seek baseline (`test_s3_seek_baseline.py`, `h264_4k_g250_b2`) — **PASS**

Headless path: each sample is a fresh `nvdec_decode_frame` (parser/decoder recreated), feeding from the GOP sync through the target presentation index. Warmup at frame 0 excluded from stats.

**`bound_cold`** (used in C8): `gop_max / s1_sequential_fps + 60 ms` with S1 4K H.264 sequential fps **225.24** and `gop_max` from `probe_clip`. Headless test also uses `max(bound_formula, 1.15 × warmup full-GOP seek)` so a shared GPU does not flake the gate.

| Metric | Value |
|--------|-------|
| `gop_max` | 249 |
| `bound_cold` | **1165.49 ms** |
| Full-GOP target (frame 248) | 1132.19 ms |
| Cold seek p50 (35 targets) | 478.47 ms |
| Cold seek p95 | **1086.37 ms** |

### GATE S3

| Criterion | Threshold | Result |
|-----------|-----------|--------|
| Cold seek p95 | ≤ `bound_cold` | **PASS** (1086.37 ≤ 1165.49) |
| Full-GOP cold seek | ≤ `bound_cold` | **PASS** (1132.19 ≤ 1165.49) |

**Fix (Tasks 3–4):** display callback index must be `sync_pres + display_serial`, not `display_serial` alone, when decode starts mid-clip.

**NVDEC NV12 copy:** chroma on the mapped frame starts at `pitch * display_height` (`ulTargetHeight`), not `pitch * coded_height`.

## S4 — reverse shuttle (four fixtures)

**S4 fixtures** (Timeline dropdown): `h264_1080_intra`, `h264_1080_gop2`, `h264_1080_g30_b2`, `h264_4k_g250_b2` — see `v1d.ngn.fixtures.S4_FIXTURE_CHOICES`.

**Timeline ([_archive/PLAN_04_TL_SLIDER.md](../_archive/PLAN_04_TL_SLIDER.md), 2026-10):** Hold **←** / **→** after 0.25 s plays at clip fps with **scrubbing on** (`tier=proxy` when `.v1dproxy` is ready, else `snap`); **release** settles **`tier=exact`**. Tap ±1 uses the same scrub-on path, then exact on release. This matches the *idea* of the headless bench below (step backward/forward with scrubbing), not exact-NVDEC on every index.

**Headless bench:** `./tools/s4_reverse_bench.py` (Kit Python + built `v1d.cor`). Re-run after engine changes; paste JSON into this table if gates move.

| Fixture | tier (measured 2026-03-22) | latency p50 ms | latency p95 ms | keeps fps? |
|---------|---------------------------|----------------|----------------|------------|
| `h264_1080_intra` | exact | 36.18 | 106.41 | yes |
| `h264_1080_gop2` | exact | 15.29 | 52.11 | yes |
| `h264_1080_g30_b2` | snap | 0.0* | 0.0* | yes |
| `h264_4k_g250_b2` | snap | 0.0* | 0.0* | yes |

\*Snap publishes while decode catches up; `latency_us` on presented snap frames was 0 in this run (tier still `snap`). **4K in Kit:** after proxy build completes, hold/scrub often shows **`tier=proxy`**; the bench does not wait for a warm `.v1dproxy` and may still report mostly `snap` on a cold open.

**GATE S4 (Phase 1 comparison shell):** intra and GOP-2 stay `exact` with p95 ≤ 120 ms on the bench’s reverse steps; long GOP may be `snap` but must advance at ≥ ~60% of clip fps over 3 s (`keeps_fps`). All four fixtures passed on reference GPU (2026-03-22). **GUI:** [GUI_TEST_PLAN.md](GUI_TEST_PLAN.md) §2.2, §4 — spot-check all four after shuttle changes; re-record here only if a gate fails.

## Phase 2 — proxy tier

| Gate | Command / test | Result (RTX 2060 12 GiB) |
|------|----------------|---------------------------|
| **C11** build | `test_proxy_c11.py`, `test_proxy_c11_atomic.py`; all fixtures: `V1D_C11_ALL=1` | All fixtures ≥ 0.5× S1 (e.g. `h264_1080_gop2` ~28 fps, `h264_4k_g250_b2` ~1.86 fps); atomic rename via `.building` |
| **C12** 4K scrub | `V1D_C12_4K=1 test_proxy_c12_4k.py` | p95 ≤ 20 ms; proxy barcode vs target (24 samples) |

Settings: `exts."v1d.cor".proxy_height` (270), `proxy_vram_mb` (256). While scrubbing with proxy ready, engine publishes `tier=proxy`; on settle, `exact`.

## A — Preview audio (`PLAN_07_AUDIO.md`)

Machine: same as S0. Spike runner: `tools/run_a0_audio_spike.sh` (`/exts/v1d.pv/a0_audio_spike=true`). Fixture: `tests/fixtures/h264_1080_aac_beep.mp4` (`tools/gen_fixtures.py h264_1080_aac_beep`).

APIs (Kit 110.3): `carb.audio.acquire_data_interface()`, `acquire_playback_interface()`, `create_sound_from_file(path, streaming=True)`, `playback.create_context()`, `context.play_sound(sound)`, `context.update()` on app tick, `voice.is_playing()`.

| Id | Container / file | Result | Notes |
|----|------------------|--------|--------|
| **A0** | MP4 (H.264 + AAC-LC) | **FAIL** | `failed to identify the format of sound` — carb.audio docs list WAV/FLAC/Ogg/MP3/Opus, not MP4/M4A |
| **A0′** | M4A (ffmpeg `-c:a copy`) | **FAIL** | Same `SoundDataError` |
| **A0″** | WAV (ffmpeg `-vn`, dev extract) | **PASS** | 5 s play; `is_playing` true then PASS at 5 s |

### GATE A0 (preferred path: stream open clip MP4)

| Criterion | Result |
|-----------|--------|
| `create_sound_from_file` on open MP4, no product FFmpeg | **FAIL** — stop Phase 1 per plan; revise plan before in-tree demux or sidecar |

**A0b (cache leg, 2026-10-16):** `ffmpeg -vn -c:a pcm_s16le` on `h264_1080_aac_beep.mp4` → WAV in **0.05 s**, **960590** bytes. Carb already **PASS** on that WAV (A0″). Not a product link. **A1–A4** and a long-clip extract time are still open.

**A0b follow-up (2026-10-17):** a full-file WAV extract **while the clip is open** contended with NVDEC and made play laggy. Extract-on-open is disabled. Streaming an **already written** WAV did not re-read the MP4, and that clip’s audio played. `context.update()` must run or a voice can stay virtual; the A0 spike called it on the app tick. Do not put that call in `tick_playback`.

## U — Upscaler (`v1d.ups`, PLAN_04)

| Id | Status | Notes |
|----|--------|-------|
| **U0** | **Pass** (2026-10-11) | `../v1d_ups/build.sh`: prebuilt `realesrgan-ncnn-vulkan` + `realcugan-ncnn-vulkan` (Real-ESRGAN **v0.2.5.0** portable zip for weights; nihui **20220728** for CUGAN). 64×64 PNG → 256×256: `fake`, `realesrgan`, `realcugan`. Source compile optional: `V1D_UPS_BUILD_SOURCE=1` (needs `glslangValidator`, clean LTO for libwebp). |
| **U1** | Manual | [GUI_TEST_PLAN.md](GUI_TEST_PLAN.md) §5.1 — six combo labels; idle status without clip |
| **U2** | Manual | §5.2–5.3 — GOP 2 fixture, **Real-ESRGAN**, wipe + scrub still works; `check_licenses.sh` clean |
| **U3** | **Recorded fail** (optional) | `seedvr2`, `flashvsr`, `video2x`, `rve`: no `venv/<id>` / `lib/engine_*.py` (build.sh SKIP). Dropdown rows stay; status shows stderr. |

Headless: `test_ups_run.py` (fake). Prefix CLI: `v1d_ups/bin/upscale-frame --engine <id> --input in.png --output out.png`.

## PLAN_DRAG-DROP_RENDER_SAVE gates

| Id | Status | Pass criterion |
|----|--------|----------------|
| **M0** | **Interim PASS (reopen)** | Python `ensure_media_path` + `open_clip` switch; headless `test_media_switch_m0.py` records reopen ms. C++ LRU pool **not** landed — target ≤ 33 ms @ 1080p30 still applies to pool. |
| **D0** | **Interim** | `omni.ui` `Frame.set_drop_fn` on timeline strip; **Add Video…** + File menu import. Native `drop_support` ext not in local cache — verify Nemo on next Kit check. |
| **E0** | **Interim** | Render uses `h264_nvenc` via ffmpeg on PNG sequence from GPU frames (`v1d.rnd`). In-engine NVENC+muxer **not** landed. |
| **E1** | Waived v1 | E0 interim path; revisit `omni.videoencoding` when in-engine encode ships. |
| **X0** | Pending | In-tree mux when C++ encode path lands. |
