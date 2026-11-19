#!/usr/bin/env bash
# Rebuild v1d.cor _scrub.so (release) on LMDE without a full repo.sh when convert.fatbin is already present.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${ROOT}/.local/bin:${PATH}"

mkdir -p "${ROOT}/.local/bin"
if [[ ! -x "${ROOT}/.local/bin/nvcc" ]]; then
  cat >"${ROOT}/.local/bin/nvcc" <<'STUB'
#!/usr/bin/env bash
out=""
args=("$@")
for i in "${!args[@]}"; do
  if [[ "${args[$i]}" == "-o" && $((i+1)) -lt ${#args[@]} ]]; then
    out="${args[$((i+1))]}"
  fi
done
if [[ -n "$out" && -f "$out" ]]; then exit 0; fi
echo "nvcc: install nvidia-cuda-toolkit or keep existing fatbin at $out" >&2
exit 1
STUB
  chmod +x "${ROOT}/.local/bin/nvcc"
fi
if [[ ! -e "${ROOT}/.local/bin/g++-12" ]]; then
  ln -sf "$(command -v g++)" "${ROOT}/.local/bin/g++-12"
fi

FFNV="${ROOT}/source/extensions/v1d.cor/third_party/ffnvcodec/dynlink_cuda.h"
if [[ ! -f "${FFNV}" ]]; then
  echo "Missing ${FFNV}. Run: sudo ${ROOT}/scripts/lmde-bootstrap.sh (installs libffmpeg-nvenc-dev) or clone nv-codec-headers into third_party/ffnvcodec." >&2
  exit 1
fi

cd "${ROOT}/_compiler/gmake2"
make --stop config=release_x86_64 -j"$(nproc)" v1d.cor.python
echo "OK: ${ROOT}/_build/linux-x86_64/release/exts/v1d.cor/v1d/ngn/_scrub.cpython-312-x86_64-linux-gnu.so"
