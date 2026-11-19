#!/usr/bin/env bash
# Align Debian 550 user-space NVIDIA libs (CUDA, GLX/Vulkan) with loaded kernel 550.x.
# Use when libcuda was fixed but libGLX_nvidia is still 615.x (Kit: no Vulkan device, cuvid fails).
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi

KVER="$(sed -n 's/.*Kernel Module  *\([0-9.]*\).*/\1/p' /proc/driver/nvidia/version 2>/dev/null | head -1 || true)"
CUR="/usr/lib/x86_64-linux-gnu/nvidia/current"
GLX="$(readlink -f /usr/lib/x86_64-linux-gnu/libGLX_nvidia.so.0 2>/dev/null || true)"
CUDA="$(readlink -f /usr/lib/x86_64-linux-gnu/libcuda.so.1 2>/dev/null || true)"

if [[ -z "$KVER" ]]; then
  echo "No NVIDIA kernel module loaded." >&2
  exit 1
fi

echo "Kernel module: ${KVER}"
echo "libcuda.so.1:  ${CUDA}"
echo "libGLX_nvidia: ${GLX}"

export DEBIAN_FRONTEND=noninteractive

need_cuda=0
need_glx=0
[[ "$CUDA" != *"/nvidia/current/"* && "$CUDA" != *".${KVER}"* ]] && need_cuda=1
[[ -n "$GLX" && "$GLX" != *".${KVER}"* ]] && need_glx=1

if [[ "$need_cuda" -eq 0 && "$need_glx" -eq 0 ]]; then
  echo "CUDA and GLX already match kernel (${KVER})."
  nvidia-smi | head -3 || true
  exit 0
fi

echo ">>> Installing Debian 550 GL/Vulkan + CUDA user libraries…"
apt-get install -y --reinstall \
  nvidia-alternative \
  libcuda1 \
  libnvidia-ml1 \
  libglx-nvidia0 \
  libnvidia-glcore \
  libnvidia-glvkspirv \
  libnvidia-eglcore

if [[ -d "$CUR" ]]; then
  for base in libcuda libnvidia-ml; do
    [[ -e "${CUR}/${base}.so.1" ]] && ln -sf "${CUR}/${base}.so.1" "/usr/lib/x86_64-linux-gnu/${base}.so.1"
    [[ -e "${CUR}/${base}.so" ]] && ln -sf "${CUR}/${base}.so" "/usr/lib/x86_64-linux-gnu/${base}.so"
  done
fi

if command -v update-glx >/dev/null; then
  update-glx --set glx nvidia || true
fi

echo "After fix:"
readlink -f /usr/lib/x86_64-linux-gnu/libcuda.so.1 || true
readlink -f /usr/lib/x86_64-linux-gnu/libGLX_nvidia.so.0 || true
nvidia-smi | head -5 || true
if command -v vulkaninfo >/dev/null && [[ -n "${DISPLAY:-}" ]]; then
  VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json vulkaninfo --summary 2>&1 | head -8 || true
fi
