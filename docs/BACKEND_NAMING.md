# Backend naming (2–3 letters)

Kit **extension ids** and Python **module** suffixes stay short and unique. GUI window titles stay plain (**Preview**, **Timeline**).

| Tag | Kit ext | Python module | Role |
|-----|---------|---------------|------|
| **cor** | `v1d.cor` | `v1d.cor` | Session bootstrap |
| **ngn** | (in cor) | `v1d.ngn` | NVDEC/CUDA (`Engine`, `ScrubSession`, headless serve). Tag **ngn** (not `eng`) so it is not read as “English”. |
| **kit** | (in cor) | `v1d.kit` | Shared Window menu helpers |
| **pv** | `v1d.pv` | `v1d.pv` | Preview + shell UI |
| **tl** | `v1d.tl` | `v1d.tl` | Timeline controls |
| **ups** | `v1d.ups` | `v1d.ups` | Upscaler window (frame snapshot + wipe) |
| **rnd** | `v1d.rnd` | `v1d.rnd` | Render composition window |

**Kit application** (not an extension): `source/apps/v1d.app.kit` → app id **`v1d.app`** (loads cor + pv + tl + ups).

Settings: `/exts/v1d.<tag>/…`. Public types keep readable names (`Engine`, `ScrubSession`) inside `v1d.ngn`.
