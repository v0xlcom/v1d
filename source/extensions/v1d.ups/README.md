# v1d.ups — Upscaler

Kit window **Upscaler**: dropdown of six external engines, **Upscale frame** (snapshot of Preview at `min(960, w)` × `min(540, h)`), wipe compare (original left / upscaled right).

- Menu: **v1d → Window → Upscaler** (not in default dock JSON).
- Setting: `/exts/v1d.ups/root` default `../v1d_ups`.
- Contract: `$root/bin/upscale-frame --engine <id> --input in.png --output out.png`.

Engine ids: `seedvr2`, `flashvsr`, `realesrgan`, `realcugan`, `video2x`, `rve` (see [PLAN_04_UPS.md](PLAN_04_UPS.md)).

Build the product engine: `../../../repo.sh build -r` from repo root. Build inference prefix: `../v1d_ups/build.sh`.
