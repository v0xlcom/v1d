#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# PLAN_07 A0 follow-up: carb.audio on AAC-in-M4A (dev ffmpeg extract; not product path).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLIP="${ROOT}/tests/fixtures/h264_1080_aac_beep.mp4"
M4A="${ROOT}/_build/a0_audio_spike.m4a"
if [[ ! -f "$CLIP" ]]; then
  python3 "${ROOT}/tools/gen_fixtures.py" h264_1080_aac_beep
fi
ffmpeg -y -hide_banner -loglevel error -i "$CLIP" -vn -c:a copy "$M4A"
export V1D_A0_CLIP="$M4A"
"${ROOT}/tools/run_a0_audio_spike.sh" "$@"
