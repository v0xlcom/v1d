#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${ROOT}/mcp/.venv"
REQ="${ROOT}/mcp/requirements.txt"

if ! command -v uv >/dev/null 2>&1; then
  echo "mcp/run-server.sh: uv not on PATH (install: https://docs.astral.sh/uv/)" >&2
  exit 1
fi

if [[ ! -x "${VENV}/bin/python" ]]; then
  uv venv "${VENV}"
fi
uv pip install -q -r "${REQ}" -p "${VENV}/bin/python"

export V1D_WORKSPACE_ROOT="${V1D_WORKSPACE_ROOT:-${ROOT}}"
exec "${VENV}/bin/python" "${ROOT}/mcp/v1d_mcp_server.py"
