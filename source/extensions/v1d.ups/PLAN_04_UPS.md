# PLAN_04_UPS — Upscaler window (`v1d.ups`)

Workspace: `.`. Model builds live in `../v1d_ups` (sibling tree, not this git repo). **Execute this file** when implementation starts. This file is the spec; it does not build anything.

Source of the six names: [6 Best Open Source Video Upscalers in 2026](https://www.videoproc.com/video-editor/open-source-video-upscaler.htm) (Joakim Kling, updated 2026-09-01).

## Goal

A Kit extension **`v1d.ups`**, window title **Upscaler**, independent of `v1d.pv` and `v1d.tl`. It depends on **`v1d.cor`** only (plus `omni.ui` and `omni.kit.menu.utils` for the window).

The window has:

1. A dropdown of the six tools below.
2. A button **Upscale frame** that snapshots the frame currently shown in Preview and runs the selected tool on that image.
3. Its own preview: a wipe slider. Left of the bar is the original snapshot. Right of the bar is the upscaled image. Both are drawn at the same on-screen size.

Success: with a clip open, choosing **Real-ESRGAN** and pressing **Upscale frame** shows that pair in the Upscaler window, and dragging the bar reveals one side or the other. The other five entries either complete the same gesture on a small fixture or stop on a recorded gate in `docs/SPIKES.md`.

## Dropdown

| Label | What it is | Build | Default for this button |
|-------|------------|-------|-------------------------|
| SeedVR2 | Diffusion video restorer (ByteDance Seed). 3B and 7B, FP16 / FP8 / GGUF. | Official inference tree, own venv | Smallest official variant that accepts a still (prefer 3B FP8 or GGUF). One frame in, one frame out. |
| FlashVSR | One-step streaming diffusion VSR. Officially 4×. | Official tree + Block-Sparse Attention, own venv | v1.1, 4×, one frame. |
| Real-ESRGAN | Frame GAN. ncnn Vulkan build. | [xinntao/Real-ESRGAN-ncnn-vulkan](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan) from source | `realesrgan-x4plus` |
| Real-CUGAN | Anime CUNet. ncnn Vulkan build. | [nihui/realcugan-ncnn-vulkan](https://github.com/nihui/realcugan-ncnn-vulkan) from source | SE model, 4× (Pro and Nose stop at 2×) |
| Video2X | Framework, not a model. Engines include Real-ESRGAN, Real-CUGAN, and Anime4K. | [k4yt3x/video2x](https://github.com/k4yt3x/video2x) from source into the `v1d_ups` prefix | Engine **Anime4K**, scale 4. Anime4K is the algorithm this row adds. The Real-ESRGAN and Real-CUGAN rows stay on their own ncnn binaries. |
| REAL Video Enhancer | Archived GUI (2026-07-13) over NCNN / TensorRT / PyTorch models. | Last commit of [TNTwise/REAL-Video-Enhancer](https://github.com/TNTwise/REAL-Video-Enhancer), Linux headless entry only | **Nomos8K**, the model the article measured |

Confirm each clone URL and tag at build time. A 404 or a missing single-image entry point is a **GATE** for that row: write the numbers and the blocker in `docs/SPIKES.md` and stop that row. Leave the other rows in the dropdown. Do not silently point the row at a different project.

## What the button upscales

Preview presents `min(960, source_width)` × `min(540, source_height)`, even, RGBA8 (`ScrubSession.open_clip` → `Engine::set_output_size`). **Upscale frame** uses that present image: the pixels on screen, not a second full-resolution decode.

`poll_frame` is preview-only. `v1d.ups` must not call it. The present ring (`kDefaultHoldPolls = 2`) recycles the device pointer, and `v1d.pv` does not keep the pointer.

Snapshot path (only `v1d.cor` change):

- At publish, the engine D2D-copies the presented RGBA into one stable device buffer, `latest`.
- Expose `latest` on `Engine` / `ScrubSession`: `ptr`, `width`, `height`, `stride`, `frame`.
- On **Upscale frame**, `v1d.ups` D2D-copies `latest` into its own original buffer, then device-to-host for the subprocess. Later presents do not overwrite the wipe’s original side.
- Cost: one extra RGBA copy per presented frame at preview size (about 2 MB at 960×540). No copy on the Python poll path.

If `latest` is empty (no clip, or no frame presented yet), the button leaves the status label on “Open a clip and wait for a frame” and does not spawn a process.

## Wipe slider

Checked against this tree’s **omni.ui 3.3.1** (Kit 110.3). `omni.image`, `omni.kit.window.preview`, and `omni.kit.widget.image_viewer` are not installed. `ByteImageProvider.set_bytes_data_from_gpu` is the display path (spike S2 passed). `DynamicTextureProvider` publishes `dynamic://` textures for RTX materials; this window does not use it.

The wipe is a clip, not a pixel-difference kernel. No Carbonite plugin, no A−B / heatmap / SSIM pass.

```
ZStack  (the preview area)
  ImageWithProvider(upscaled)          # full area, IWP_STRETCH
  Frame(width = split_px, horizontal_clipping=True)
    ImageWithProvider(original)        # width = full view width, same fill, alignment LEFT
  Placer(offset_x = split_px)
    thin Rectangle handle
```

`Frame.horizontal_clipping` crops a child that is wider than the frame. The original image’s width stays equal to the full view, so the bar cuts the picture instead of squeezing it. Both providers use the same fill policy and the same widget box. The upscaled texture is larger (2× or 4×); the GPU sampler scales it down to that box.

The handle uses the widget mouse callbacks (`mouse_pressed_fn` / `mouse_moved_fn`). There is no `Draggable` type. Releasing the handle leaves the split where it is. A `FloatSlider` under the image is optional and, if added, must drive the same split value as the handle.

Show the original as soon as the snapshot copy finishes. Replace the upscaled provider when the subprocess writes its PNG and the result is uploaded with `set_bytes_data_from_gpu`. Status line: tool name, scale, wall time, error text.

Inference runs on a worker thread. The Kit main thread only copies the snapshot, spawns, and uploads the result on a later update tick.

## Process boundary

PyTorch, ncnn, FFmpeg, and TensorRT stay in `../v1d_ups`. They are not linked into `v1d.cor` or any shipped `.so`. `tools/check_licenses.sh` still forbids MLT, FFmpeg, x264/x265, cudart, and cublas in product `NEEDED` entries. Kit’s Python must not `import torch`.

One contract, one setting:

- `/exts/v1d.ups/root` default `../v1d_ups`
- Executable: `$root/bin/upscale-frame --engine <id> --input in.png --output out.png`
- Engine ids: `seedvr2`, `flashvsr`, `realesrgan`, `realcugan`, `video2x`, `rve`
- Exit 0 and a larger PNG on success. Non-zero with a short stderr line on failure.
- Each heavy Python tool gets its own venv under `$root/venv/<id>`. The wrapper activates that venv. ncnn tools are plain binaries under `$root/bin/`.
- Weights live in `$root/models/`, pinned URLs and checksums in `$root/models/SHA256SUMS`. Weights are not committed to the v1d repo.

```
../v1d_ups/
  bin/upscale-frame
  bin/realesrgan-ncnn-vulkan
  bin/realcugan-ncnn-vulkan
  venv/seedvr2/
  venv/flashvsr/
  venv/video2x/
  venv/rve/
  src/<pinned clones>
  models/
  THIRD_PARTY.md
  build.sh
```

`build.sh` configures, builds, and installs those prefixes. A failed row is recorded and skipped; the script continues to the next row and exits non-zero if any required row failed.

## UI shell

Follow `v1d.tl`: `omni.ext.IExt` + `MenuHelperExtension`, `wire_window_menu` / `unwire_window_menu` from `v1d.kit.window_menu`, title from `/exts/v1d.ups/window_title` default **Upscaler**. Shutdown unregisters nothing on `ScrubSession` unless a listener was added; if one is added, remove it in `on_shutdown`.

Layout, top to bottom: dropdown (`ui.ComboBox`), button **Upscale frame**, status `ui.Label`, wipe `ZStack`.

App kit `source/apps/v1d.app.kit` gains `"v1d.ups" = {}` after `v1d.tl`. Dock layout in `v1d.pv` stays as it is. The window opens from **v1d → Window → Upscaler**.

## Files

New extension (Python only, same premake pattern as `v1d.tl`):

| Path | Role |
|------|------|
| `source/extensions/v1d.ups/config/extension.toml` | id `v1d.ups`, deps `omni.ui`, `omni.kit.menu.utils`, `v1d.cor` |
| `source/extensions/v1d.ups/premake5.lua` | `project_ext` + link `python/v1d` |
| `source/extensions/v1d.ups/python/v1d/ups/__init__.py` | export `V1dUpscalerExtension` |
| `source/extensions/v1d.ups/python/v1d/ups/extension.py` | window, combo, button, wipe |
| `source/extensions/v1d.ups/python/v1d/ups/wipe.py` | clip frame + handle |
| `source/extensions/v1d.ups/python/v1d/ups/run.py` | subprocess wrapper, worker thread |
| `source/extensions/v1d.ups/docs/Overview.md` | one screen |

Touched product files:

| Path | Change |
|------|--------|
| `source/extensions/v1d.cor/plugins/v1d.cor/engine.cpp` (+ header, binding, `ngn.py`, `session.py`) | `latest` buffer and read API |
| `source/apps/v1d.app.kit` | load `v1d.ups` |
| `docs/BACKEND_NAMING.md` | row **ups** / `v1d.ups` / Upscaler |
| `docs/UI_EXTENSIONS.md` | row for the window |
| `ARCHITECTURE.md` | one line under Kit extensions, link here |
| `PROGRESS.md` | pointer under After PLAN_01 |
| `THIRD_PARTY.md` | pointer: inference binaries and weights live in `v1d_ups`, licenses listed there |
| `docs/GUI_TEST_PLAN.md` | manual wipe + six-entry check |
| `docs/SPIKES.md` | U0–U3 results when run |
| `AGENTS.md` | active-work line points at this file |

`../v1d_ups` is created by `build.sh` during implementation. Do not copy code from `../v1d_ref/`.

## Gates

| Id | Pass |
|----|------|
| U0 | `build.sh` produces `bin/upscale-frame`. Each engine id accepts a 64×64 PNG and writes a larger PNG, or that id is a recorded fail in `docs/SPIKES.md`. |
| U1 | Kit shows **Window → Upscaler**, six labels, button idle with no `latest` frame. |
| U2 | S4 fixture, Real-ESRGAN: original appears, then upscaled; dragging the bar changes the clip; scrub in Preview still updates. `check_licenses.sh` stays clean. |
| U3 | Same fixture, other five ids, one frame each, or a recorded per-id fail (VRAM, missing headless entry, license). |

Default `./tools/run_tests.sh` does not download weights. A fake engine in `run.py` tests (temp dir, script that scales with a deterministic resize) covers spawn, timeout, and PNG upload. Opt-in GPU run: `V1D_UPS=1`.

## Out of scope

- Exporting a whole clip.
- Decoding the source frame at native resolution.
- Neighbor frames for SeedVR2 or FlashVSR temporal windows.
- Heatmap, A−B, SSIM, or any C++ image kernel.
- `omni.image` and `DynamicTextureProvider`.
- Linking FFmpeg, PyTorch, ncnn, or TensorRT into the v1d product.
- Editing the archived REAL Video Enhancer upstream.

## Risks

| Risk | Response |
|------|----------|
| SeedVR2 or FlashVSR exceeds local VRAM, or Block-Sparse Attention fails to build | U3 fail for that id. Dropdown entry remains, status shows the stderr line. |
| REAL Video Enhancer has no headless one-frame command | U3 fail for `rve`. Do not drive its GUI. |
| A weight license rejects this use | Disable that entry, note the license in `v1d_ups/THIRD_PARTY.md`. |
| Video2X’s prefix needs FFmpeg | FFmpeg stays inside `v1d_ups`. Re-run `tools/check_licenses.sh` on the v1d `.so`. |
| One-frame diffusion output looks different from the article’s video tests | Status can say `1 frame`. Do not add neighbor fetches in this plan. |
