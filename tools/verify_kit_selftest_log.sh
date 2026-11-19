#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
LOG="${1:?log path}"
if [[ ! -f "$LOG" ]]; then
  echo "verify_kit_selftest_log: missing $LOG" >&2
  exit 1
fi
if ! grep -q '\[v1d.pv selftest\] pass=True' "$LOG"; then
  echo "verify_kit_selftest_log: selftest did not pass" >&2
  exit 1
fi
# C10 runs with --no-window; omni.rtx may log GPU Foundation errors while v1d NVDEC selftest still passes.
if grep -E '\[Error\] \[(v1d\.|v1d\.cor|v1d\.pv|v1d\.tl|v1d\.ups)' "$LOG" >/dev/null; then
  echo "verify_kit_selftest_log: v1d [Error] lines in log:" >&2
  grep -E '\[Error\] \[(v1d\.|v1d\.cor|v1d\.pv|v1d\.tl|v1d\.ups)' "$LOG" >&2 || true
  exit 1
fi
echo "verify_kit_selftest_log: OK"
