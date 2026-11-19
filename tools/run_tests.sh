#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REL="$ROOT/_build/linux-x86_64/release"
# shellcheck source=/dev/null
source "${ROOT}/scripts/nvidia-userspace-env.sh"
export PYTHONPATH="${REL}/exts/v1d.cor:${PYTHONPATH:-}"
export LD_LIBRARY_PATH="${REL}/kit:${LD_LIBRARY_PATH:-}"
exec "${REL}/kit/python/bin/python3" -m unittest discover -s "${ROOT}/source/extensions/v1d.cor/python/tests" -p 'test_*.py' "$@"
