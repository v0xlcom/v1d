# Python (v1d)

**Purpose:** `v1d.ngn.Engine`, `ScrubSession`, headless RPC.

**Path:** `source/extensions/v1d.cor/python/v1d/ngn/`

**Version:** `_build/.../kit/python/bin/python3` + `PYTHONPATH=exts/v1d.cor` (see BUILD_NOTES).

**Allowed:** `./tools/run_tests.sh`; `./tools/v1d`; bundled Kit Python 3.12 for extension code.

**Forbidden:** `import omni` from `v1d.ngn` (engine stays headless-clean).

**Detail:** [docs/BUILD_NOTES.md](../../docs/BUILD_NOTES.md).
