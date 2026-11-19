#!/usr/bin/env bash
# One-time LMDE host setup: fix interrupted CUDA apt, install build deps, rebuild v1d.
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo ">>> Fixing dpkg (nvidia-installer-cleanup / GLX alternatives)…"
if dpkg -l nvidia-installer-cleanup 2>/dev/null | grep -qE '^iF|^iU'; then
  echo update-glx update-glx/activate select mesa | debconf-set-selections || true
  echo glx-alternative-mesa glx-alternative-mesa/use_mesa boolean true | debconf-set-selections || true
  # postinst cannot run noninteractively while nvidia-installer exists (Debian #exit 30).
  rm -f /usr/bin/nvidia-installer /usr/bin/nvidia-uninstall
  dpkg --configure -a || true
fi
apt-get install -y -f

echo ">>> Installing build and test dependencies…"
apt-get install -y \
  ripgrep \
  g++-12 \
  libffmpeg-nvenc-dev \
  nvidia-cuda-toolkit

USER_NAME="${SUDO_USER:-lx}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo ">>> Rebuilding v1d.cor (release)…"
su - "${USER_NAME}" -c "cd '${ROOT}' && ./scripts/rebuild-cor-release.sh"

echo ">>> Full Kit staging build…"
su - "${USER_NAME}" -c "cd '${ROOT}' && ./repo.sh build -r"

echo ">>> Running tests…"
su - "${USER_NAME}" -c "cd '${ROOT}' && ./tools/run_tests.sh -v"

echo "Done. Launch GUI: ${ROOT}/scripts/launch-v1d-terminal.sh"
