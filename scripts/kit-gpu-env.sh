# SPDX-License-Identifier: MIT
# Source from Kit launch/selftest scripts. Not for interactive use.
# (Headless tests use scripts/nvidia-userspace-env.sh; do not prepend nvidia/current here — breaks Vulkan.)
# Prefer one NVIDIA Vulkan ICD so omni.rtx does not log duplicate-ICD [Error].
if [[ -z "${VK_ICD_FILENAMES:-}" ]]; then
  if [[ -f /etc/vulkan/icd.d/nvidia_icd.json ]]; then
    export VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json
  elif [[ -f /usr/share/vulkan/icd.d/nvidia_icd.json ]]; then
    export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json
  fi
fi
