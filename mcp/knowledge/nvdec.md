# NVDEC (v1d)

**Purpose:** One `cuvid` decoder per process; NV12 on GPU; device-to-device copy into frame cache.

**Path:** `source/extensions/v1d.cor/plugins/v1d.cor/nvdec_decoder.*` (and related).

**Allowed:** `cuvid*` via dynlink; `cuMemcpy2DAsync` D2D; single decoder (proxy builder borrows, never a second).

**Forbidden:** Second decode API; CPU round-trip of pixels; FFmpeg decode in the shipping path.

**Detail:** [ARCHITECTURE.md](../../ARCHITECTURE.md).
