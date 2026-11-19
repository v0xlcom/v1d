# Troubleshooting — `v1d.ups`

## Prefix missing or engines fail

```bash
../v1d_ups/build.sh
```

Prebuilt ncnn binaries + models: Real-ESRGAN portable zip (v0.2.5.0), Real-CUGAN release **20220728**. Optional source: `V1D_UPS_BUILD_SOURCE=1` (needs Vulkan `glslangValidator`, submodule HTTPS URLs in `build.sh`).

Kit setting must point at the prefix:

`/exts/v1d.ups/root` → `../v1d_ups`

## After code changes

1. **`./repo.sh build -r`** at repo root (updates `v1d.cor` + copies `v1d.ups` Python).
2. **Full quit** Kit; launch again. Reload alone may leave stale `_scrub` or extension state.

## Wipe compare

| Symptom | Likely cause |
|---------|----------------|
| Right side solid white | Upscaled texture not uploaded; rebuild for `cuda_write_rgba`; status `display upload failed` in log |
| Large white area moves with drag | Old build (separate right `Placer` + empty provider); update `wipe.py` |
| Window grows horizontally | Drag ended outside app; outer `Frame` clips; use current `wipe.py` |

Display path: downscale upscaled PNG to **snapshot size**, `cuda_write_rgba`, `set_bytes_data_from_gpu` on `_up` provider (same family as Preview).

## Headless

- `test_ups_run.py` — fake engine (no weights).
- `test_cuda_read_rgba.py` — includes `cuda_write_rgba` roundtrip.

## Logs

`~/.local/share/v1d/v1d.log` or `_build/.../logs/Kit/v1d.app/`. Search `[v1d.ups]`.
