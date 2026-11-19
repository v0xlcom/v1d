# Kit 110.3 (v1d UI)

**Purpose:** Display via `omni.ui` `ByteImageProvider.set_bytes_data_from_gpu`; app `source/apps/v1d.app.kit`.

**Path:** Build tree `_build/linux-x86_64/release/`; launch [docs/BUILD_NOTES.md](../../docs/BUILD_NOTES.md).

**Version:** Kit from `./repo.sh build -r` at **repo root** (not `v1d_ref/kit-app-template`).

**Allowed:** Symbols found by `v1d_lookup_symbol` lang=kit in local `_build/` extscache, plus `kit/kernel/py/carb/input.pyi`.

**Pick docs:** `v1d_sources` with the task words. Index: `mcp/sources.json`. Local stubs outrank public omni.ui pages.

**Forbidden:** Build product in `../v1d_ref/kit-app-template`; `ui.ViewportWidget` unless lookup proves it exists.

**Detail:** [docs/GUI_TEST_PLAN.md](../../docs/GUI_TEST_PLAN.md).
