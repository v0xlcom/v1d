#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/tests/fixtures/h264_1080_g30_b2.mp4"
OUT="${ROOT}/tests/fixtures/bad"
mkdir -p "$OUT"
dd if="$SRC" of="${OUT}/truncated.mp4" bs=4096 count=1 status=none
ffmpeg -y -hide_banner -loglevel error -f lavfi -i color=c=black:s=64x64:d=0.1 -c:v libvpx-vp9 -f mp4 "${OUT}/vp9.mp4"
ffmpeg -y -hide_banner -loglevel error -f lavfi -i color=c=black:s=64x64:d=0.1 -pix_fmt yuv444p \
  -c:v libx264 -profile:v high444 -f mp4 "${OUT}/h264_444.mp4"
ffmpeg -y -hide_banner -loglevel error -f lavfi -i color=c=black:s=64x64:d=0.1 -c:v libx264 \
  -movflags frag_keyframe+empty_moov -f mp4 "${OUT}/fragmented.mp4"
echo "Wrote bad fixtures under ${OUT}"
