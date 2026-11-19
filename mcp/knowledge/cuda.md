# CUDA (v1d)

**Purpose:** Driver API only via `ffnvcodec` dynlink; primary context; fatbin kernels at build time.

**Path:** `source/extensions/v1d.cor/plugins/v1d.cor/` (native engine).

**Version:** `nvcc --version` (MCP `cuda_probe`).

**Allowed:** `cuDevicePrimaryCtxRetain`, `cuModuleLoadData`, fatbin arches `sm_75`, `sm_86`, `sm_90`, PTX `compute_90`; host `g++-12` via `V1D_NVCC_CCBIN`.

**Forbidden:** Link or load `cudart`, `cublas`; launch kernels from MCP; unsandboxed GPU jobs need `/dev/nvidia*`.

**Detail:** [docs/BUILD_NOTES.md](../../docs/BUILD_NOTES.md), [docs/SPIKES.md](../../docs/SPIKES.md) S0.
