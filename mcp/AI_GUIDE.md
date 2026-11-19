# v1d MCP — agent guide

Workspace: `V1D_WORKSPACE_ROOT` (default `.`). Archived spec: `_archive/PLAN_02_MCP.md`.

## Priority order

1. User runs `/v1d_mcp` once per Cursor CLI session → `v1d_session_activate`.
2. `v1d_constraints` + this guide (`v1d_get_ai_guide` or resource `v1d://guide/ai`).
3. `v1d_lookup_symbol` before any new `omni.*`, `carb.*`, CUDA, C++, or pybind call.
4. Kit UI, keyboard, Omniverse samples, or an external NVIDIA skill: `v1d_sources` with the task words. Open only the matched rows.
5. Builds/tests: `v1d_run_job` / `v1d_run_job_json` only (ops in `mcp/operations.json`).
6. Engine/GUI map: `./tools/v1d` or `v1d_engine`, then `v1d_describe`.
7. Kit selftest log: `v1d_tail_kit_log`; stop Kit this server started: `v1d_shutdown_kit`.

If tool list includes `create_sequence` or `insert_clip`, the MCP process is **stale MLT** — do not call those tools.

## Key paths

| Item | Path |
|------|------|
| Repo root | `.` |
| Build | `./repo.sh build -r` |
| Release tree | `_build/linux-x86_64/release` |
| Engine ext | `source/extensions/v1d.cor` → `exts/v1d.cor` |
| UI | `source/extensions/v1d.pv`, `v1d.tl` |
| Headless CLI | `tools/v1d` |
| Kit binary | `_build/linux-x86_64/release/kit/kit` |
| App kit | `source/apps/v1d.app.kit` |
| Kit selftest log | `_build/kit_selftest.log` |
| Fatbin | `exts/v1d.cor/v1d/ngn/convert.fatbin` |
| Reference (read only) | `../v1d_ref/` |
| Job inbox | `workspace/inbox/` |
| Session flag | `workspace/.v1d_mcp_active` |

Knowledge cards: `mcp/knowledge/*.md`. Catalog: `mcp/catalog.json`. External skills and docs: `mcp/sources.json` via `v1d_sources`.

## CUDA

Driver API via `ffnvcodec` dynlink. Primary context. Fatbin: sm_75, sm_86, sm_90 + PTX compute_90. `V1D_NVCC_CCBIN=g++-12`. No `cudart` / `cublas`. Probe: job `cuda_probe` (unsandboxed).

Manual: https://docs.nvidia.com/cuda/

## C++

Engine under `plugins/v1d.cor` — no Carb/omni includes. Bindings may use C++20 if the build allows.

## Python

`v1d.ngn.Engine`, `ScrubSession`. Tests: `./tools/run_tests.sh`. Import check: job `headless_import`.

## Kit

Kit **110.3** from repo-root build. Display: `ByteImageProvider.set_bytes_data_from_gpu`. Launch: `docs/BUILD_NOTES.md`, `scripts/launch-v1d-terminal.sh`. Selftest: job `kit_selftest`.

## Sources

`v1d_sources(task)` reads `mcp/sources.json` and returns the matching rows (id, url or local path, and a short note). `/v1d_mcp` does not download those pages. Open a URL only after it appears in a match. Public pages marked latest do not override a local stub. `v1d_lookup_symbol` still gates a new `omni.*`, `carb.*`, or CUDA call.

## Engine (headless)

`tools/v1d` subcommands (PLAN_01 D7): `serve`, `open`, `reload`, `scrub`, `play`, `status`, `set`, `fixture`. MCP `v1d_engine` wraps the same CLI. `v1d_describe` → `status`.

## USD

Use `usd_composer_mcp` — not v1d tools.

## Companions

Inkscape, OpenChatCut, Kdenlive, USD Composer — see `v1d_catalog`. Do not duplicate their MCP tools here.

## Troubleshooting

- `v1d_doctor` — paths, `operations.json`, `nvcc`, `nvidia-smi` when GPU visible.
- Build registry timeout: copy extscache from `v1d_ref/kit-app-template` per `docs/BUILD_NOTES.md`.
- GPU tests: unsandboxed shell; `run_tests` with `gpu: false` sets `V1D_GPU_TESTS=0`.
- Kit hung: `v1d_tail_kit_log` then `v1d_shutdown_kit` (only processes this server started).
- Wrong API: run `v1d_lookup_symbol` — miss means do not write the call.
