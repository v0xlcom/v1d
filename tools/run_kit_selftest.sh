#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# C10: Kit UI selftest (GPU + display).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "${ROOT}/scripts/kit-gpu-env.sh"
REL="${ROOT}/_build/linux-x86_64/release"
CLIP="${ROOT}/tests/fixtures/h264_1080_g30_b2.mp4"
LOG="${ROOT}/_build/kit_selftest.log"
KIT="${REL}/kit/kit"
APP_KIT="${ROOT}/source/apps/v1d.app.kit"

if [[ ! -x "$KIT" ]]; then
  echo "Missing Kit build: ${KIT}" >&2
  exit 1
fi
if [[ ! -f "$CLIP" ]]; then
  echo "Missing fixture: ${CLIP}" >&2
  exit 1
fi

export LD_LIBRARY_PATH="${REL}/kit:${LD_LIBRARY_PATH:-}"

GUI_KIT_ARGS=(
  --/app/window/enabled=true
  --/app/window/create=true
  --/crashreporter/enabled=false
  --/exts/omni.gpu_foundation/startup/skipErrorDialogs=true
  --/renderer/multiGpu/enabled=false
  --/renderer/multiGpu/autoEnable=false
  --/renderer/multiGpu/maxGpuCount=1
)

set +e
"$KIT" "$APP_KIT" \
  --ext-folder "${REL}/exts" \
  --ext-folder "${REL}/extscache" \
  --portable-root "${REL}" \
  "${GUI_KIT_ARGS[@]}" \
  --/exts/v1d.cor/clip="${CLIP}" \
  --/exts/v1d.pv/selftest=true \
  --no-window 2>&1 | tee "${LOG}"
KIT_EC=${PIPESTATUS[0]}
set -e

"${ROOT}/tools/verify_kit_selftest_log.sh" "${LOG}"
exit "${KIT_EC}"
