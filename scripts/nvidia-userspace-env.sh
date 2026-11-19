#!/usr/bin/env bash
# Source from kit-gpu-env.sh / run_tests.sh when kernel module and top-level libcuda disagree.
# Prepends Debian's /nvidia/current/ (550) to LD_LIBRARY_PATH. Permanent fix:
#   sudo scripts/fix-nvidia-userspace-550.sh

if [[ -n "${V1D_NVIDIA_USERSPACE_FIXED:-}" ]]; then
  :
elif [[ -r /proc/driver/nvidia/version ]]; then
  K="$(sed -n 's/.*Kernel Module  *\([0-9.]*\).*/\1/p' /proc/driver/nvidia/version 2>/dev/null | head -1)"
  U="$(readlink -f /usr/lib/x86_64-linux-gnu/libcuda.so.1 2>/dev/null || true)"
  CUR="/usr/lib/x86_64-linux-gnu/nvidia/current"
  if [[ -n "$K" && -n "$U" && -d "$CUR" && "$U" != *"$K"* ]]; then
    export LD_LIBRARY_PATH="${CUR}:${LD_LIBRARY_PATH:-}"
    export V1D_NVIDIA_USERSPACE_FIXED=1
  fi
fi
