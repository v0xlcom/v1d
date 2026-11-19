#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Capture Preview + Timeline + Console layout into data/ui_workspace_default.json
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "${ROOT}/scripts/kit-gpu-env.sh"
REL="${ROOT}/_build/linux-x86_64/release"
CLIP="${ROOT}/tests/fixtures/h264_1080_g30_b2.mp4"
KIT="${REL}/kit/kit"
APP_KIT="${ROOT}/source/apps/v1d.app.kit"
OUT="${ROOT}/source/extensions/v1d.pv/data/ui_workspace_default.json"

if [[ ! -x "$KIT" ]]; then
  echo "Missing Kit build: ${KIT}" >&2
  exit 1
fi

export LD_LIBRARY_PATH="${REL}/kit:${LD_LIBRARY_PATH:-}"

"$KIT" "$APP_KIT" \
  --ext-folder "${REL}/exts" \
  --ext-folder "${REL}/extscache" \
  --portable-root "${REL}" \
  --/app/window/enabled=true \
  --/app/window/create=true \
  --/crashreporter/enabled=false \
  --/exts/omni.gpu_foundation/startup/skipErrorDialogs=true \
  --/renderer/multiGpu/enabled=false \
  --/renderer/multiGpu/autoEnable=false \
  --/renderer/multiGpu/maxGpuCount=1 \
  --/exts/v1d.cor/clip="${CLIP}" \
  --/exts/v1d.pv/ui/workspace_persist=false \
  --/exts/v1d.pv/ui/capture_workspace_default=true \
  --/exts/v1d.pv/ui/capture_workspace_then_quit=true

if [[ ! -f "$OUT" ]]; then
  echo "Capture failed: missing ${OUT}" >&2
  exit 1
fi
echo "OK: ${OUT} ($(wc -c <"$OUT") bytes)"
