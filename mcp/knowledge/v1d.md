# v1d product

**Purpose:** GPU scrub viewer/engine at repo root (`v1d.cor`, `v1d.ngn`, `v1d.pv`, `v1d.tl`).

**Path:** `.`

**Version:** `./repo.sh build -r` then `tools/v1d status` or headless import via MCP `headless_import`.

**Allowed:** PLAN_01 decisions D1–D5; [docs/BUILD_NOTES.md](../../docs/BUILD_NOTES.md); [docs/SPIKES.md](../../docs/SPIKES.md); headless `./tools/v1d`.

**Forbidden:** Copy `../v1d_ref/` into `source/`; recreate `src/`; ship FFmpeg/MLT in the product.

**Detail:** [ARCHITECTURE.md](../../ARCHITECTURE.md), [_archive/PLAN_02_MCP.md](../../_archive/PLAN_02_MCP.md).
