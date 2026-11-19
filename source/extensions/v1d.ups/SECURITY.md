# Security — `v1d.ups`

## Process boundary

Kit Python must **not** `import torch` or link ncnn/FFmpeg into `v1d.cor`. All heavy inference runs in **`../v1d_ups`** via `bin/upscale-frame` and per-engine venvs (when installed).

`tools/check_licenses.sh` still forbids MLT, FFmpeg, x264/x265, cudart/cublas in product `NEEDED` entries for shipped `.so` files.

## Weights and third party

Model weights live under `v1d_ups/models/` (not in the v1d git repo). See `v1d_ups/THIRD_PARTY.md` and repo [THIRD_PARTY.md](../../../THIRD_PARTY.md).

## Secrets

Do not put API keys or personal paths into `extension.toml` commits; use local Kit settings or user overrides for `/exts/v1d.ups/root` if needed.
