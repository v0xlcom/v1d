# v1d build notes

## Build

```bash
cd /path/to/v1d
./repo.sh build -r
```

First-time extension registry: Kit’s Python `urlopen` to Azure may time out (3s) even when `curl` works. If `precache_exts` fails, ensure `~/.local/share/ov/data/exts/v2/index/*/registry.gz` exists and copy `extscache` from a working Kit 110.3 tree (`../v1d_ref/kit-app-template/_build/linux-x86_64/release/extscache`).

Engine extension: **`v1d.cor`** (`v1d.ngn` Python + native `_scrub`). UI: **`v1d.pv`**, **`v1d.tl`**.

## Headless import (`_scrub`)

```bash
EXT=_build/linux-x86_64/release/exts/v1d.cor
PY=_build/linux-x86_64/release/kit/python/bin/python3
export LD_LIBRARY_PATH=_build/linux-x86_64/release/kit
export PYTHONPATH="$EXT"
"$PY" -c "import v1d.ngn._scrub as s; print(s.__version__)"
```

## Launch GUI

```bash
ROOT=_build/linux-x86_64/release
$ROOT/kit/kit source/apps/v1d.app.kit \
  --ext-folder $ROOT/exts --ext-folder $ROOT/extscache --portable-root $ROOT
```

Or `./scripts/launch-v1d-terminal.sh`. Default clip: `--/exts/v1d.cor/clip=...`. S2 bench: `--/exts/v1d.pv/s2_bench=true`. Manual GUI checklist: [GUI_TEST_PLAN.md](GUI_TEST_PLAN.md).

## Licenses (C2)

```bash
./tools/check_licenses.sh
```

## Tests

```bash
./tools/run_tests.sh -v
V1D_C4_QUICK=1 ./tools/run_tests.sh -v
V1D_GPU_TESTS=0 ./tools/run_tests.sh   # skip GPU cases
```

`PYTHONPATH` → `exts/v1d.cor`. Fixtures: `python3 tools/gen_fixtures.py`; bad inputs: `./tools/gen_bad_fixtures.sh`.

## Kit selftest (C10)

```bash
./tools/run_kit_selftest.sh
```

Uses `v1d.app.kit`, `--/exts/v1d.cor/clip=...`, `--/exts/v1d.pv/selftest=true`. Log check: `tools/verify_kit_selftest_log.sh`.

## Headless `tools/v1d` (C13)

```bash
./tools/v1d serve
./tools/v1d open tests/fixtures/h264_1080_gop2.mp4
./tools/v1d status
./tools/v1d help
```

S4 bench: `kit/python/bin/python3 tools/s4_reverse_bench.py` — see `docs/SPIKES.md`.

Extended Phase 2 gates (slow, GPU):

```bash
V1D_C11_ALL=1 ./tools/run_tests.sh -v -p 'test_proxy_c11_all.py'
V1D_C12_4K=1 ./tools/run_tests.sh -v -p 'test_proxy_c12_4k.py'
```

Naming: [docs/BACKEND_NAMING.md](BACKEND_NAMING.md).
