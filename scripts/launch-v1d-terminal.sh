#!/usr/bin/env bash
# Foreground Kit scrub GUI — logs in terminal (desktop: Terminal=true).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/kit-gpu-env.sh"
export V1D_ROOT="${ROOT}"
export V1D_LAUNCH_SCRIPT="${SCRIPT_DIR}/launch-v1d-terminal.sh"
BUILD="${ROOT}/_build/linux-x86_64/release"
KIT="${BUILD}/kit/kit"
APP_KIT="${ROOT}/source/apps/v1d.app.kit"
STATE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/v1d"
LOG="${STATE_DIR}/v1d.log"
DEFAULT_CLIP="${ROOT}/tests/fixtures/h264_1080_g30_b2.mp4"

mkdir -p "$STATE_DIR"
cd "$ROOT"

# shellcheck source=/dev/null
source "${SCRIPT_DIR}/nvidia-userspace-env.sh"
export LD_LIBRARY_PATH="${BUILD}/kit:${LD_LIBRARY_PATH:-}"

pause_before_close() {
  echo
  echo "Log file: ${LOG}"
  read -r -p "Press Enter to close this terminal..."
}

if [[ ! -x "$KIT" ]]; then
  echo "Missing Kit build: ${KIT}"
  echo "Build the project (repo.sh build / your usual release build), then retry."
  pause_before_close
  exit 1
fi

if [[ ! -f "$APP_KIT" ]]; then
  echo "Missing app kit: ${APP_KIT}"
  pause_before_close
  exit 1
fi

CLIP_ARG=()
if [[ -n "${V1D_CLIP:-}" ]]; then
  CLIP_ARG=(--/exts/v1d.cor/clip="${V1D_CLIP}")
elif [[ -f "$DEFAULT_CLIP" ]]; then
  CLIP_ARG=(--/exts/v1d.cor/clip="${DEFAULT_CLIP}")
fi

GUI_KIT_ARGS=(
  --/app/window/enabled=true
  --/app/window/create=true
  --/crashreporter/enabled=false
  --/exts/omni.gpu_foundation/startup/skipErrorDialogs=true
  --/renderer/multiGpu/enabled=false
  --/renderer/multiGpu/autoEnable=false
  --/renderer/multiGpu/maxGpuCount=1
)

echo "Starting v1d scrub shell (GUI)…"
echo "Log: ${LOG}"

set +o errexit
"$KIT" "$APP_KIT" \
  --ext-folder "${BUILD}/exts" \
  --ext-folder "${BUILD}/extscache" \
  --portable-root "$BUILD" \
  "${GUI_KIT_ARGS[@]}" \
  "${CLIP_ARG[@]}" \
  "$@" 2>&1 | tee -a "$LOG"
kit_status=${PIPESTATUS[0]}
set -o errexit

if [[ "$kit_status" -ne 0 ]]; then
  echo "v1d exited with status ${kit_status} (error or crash — scroll above for details)."
else
  echo "v1d exited normally."
fi
pause_before_close
exit "$kit_status"
