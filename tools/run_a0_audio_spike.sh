#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# PLAN_07 A0: carb.audio streaming from MP4 (Kit + GPU env).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "${ROOT}/scripts/kit-gpu-env.sh"
REL="${ROOT}/_build/linux-x86_64/release"
CLIP="${V1D_A0_CLIP:-${ROOT}/tests/fixtures/h264_1080_aac_beep.mp4}"
LOG="${ROOT}/_build/a0_audio_spike.log"
KIT="${REL}/kit/kit"
APP_KIT="${ROOT}/source/apps/v1d.app.kit"

if [[ ! -x "$KIT" ]]; then
  echo "Missing Kit build: ${KIT}" >&2
  exit 1
fi

if [[ ! -f "$CLIP" ]]; then
  echo "Generating fixture ${CLIP} ..."
  python3 "${ROOT}/tools/gen_fixtures.py" h264_1080_aac_beep
fi

export LD_LIBRARY_PATH="${REL}/kit:${LD_LIBRARY_PATH:-}"

set +e
"$KIT" "$APP_KIT" \
  --ext-folder "${REL}/exts" \
  --ext-folder "${REL}/extscache" \
  --portable-root "${REL}" \
  --/app/window/enabled=false \
  --/app/window/create=false \
  --/crashreporter/enabled=false \
  --/exts/v1d.pv/a0_audio_spike=true \
  --/exts/v1d.pv/a0_audio_spike_clip="${CLIP}" \
  --/exts/v1d.pv/a0_audio_spike_seconds=5.0 \
  --no-window 2>&1 | tee "${LOG}"
EC=${PIPESTATUS[0]}
set -e

if grep -q '\[A0\] PASS' "${LOG}"; then
  echo "run_a0_audio_spike: PASS (see ${LOG})"
  exit 0
fi
if grep -q '\[A0\] FAIL' "${LOG}"; then
  echo "run_a0_audio_spike: FAIL (see ${LOG})" >&2
  exit 1
fi
echo "run_a0_audio_spike: inconclusive exit=${EC} (see ${LOG})" >&2
exit "${EC}"
