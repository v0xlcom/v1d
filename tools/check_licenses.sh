#!/usr/bin/env bash
# C2: shipped v1d.cor binaries must not link forbidden libs; source must not include libav/mlt.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXT="${ROOT}/_build/linux-x86_64/release/exts/v1d.cor"
FORBIDDEN_RE='mlt|libav|libsw|x264|x265|cudart|cublas|nvcuvid|libcuda'

if [[ ! -d "$EXT" ]]; then
  echo "check_licenses: missing $EXT (run ./repo.sh build -r)" >&2
  exit 1
fi

fail=0
while IFS= read -r -d '' so; do
  while read -r dep; do
    if echo "$dep" | grep -Eiq "$FORBIDDEN_RE"; then
      echo "FORBIDDEN NEEDED in $so: $dep" >&2
      fail=1
    fi
  done < <(readelf -d "$so" 2>/dev/null | awk '/NEEDED/ {print $5}' | tr -d '[]' || true)
done < <(find "$EXT" -name '*.so' -print0)

if rg -l '#include.*(libav|libsw|mlt/)' "${ROOT}/source" 2>/dev/null; then
  echo "FORBIDDEN include under source/" >&2
  fail=1
fi

if [[ ! -f "${ROOT}/THIRD_PARTY.md" ]]; then
  echo "missing THIRD_PARTY.md" >&2
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
echo "check_licenses: OK"
