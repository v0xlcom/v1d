#!/usr/bin/env bash
# Reload from in-app: new Kit + dev terminal(s) for live logs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/v1d"
LOG="${STATE_DIR}/v1d.log"
RELOAD_LOG="${STATE_DIR}/v1d-reload.log"
LAUNCH="${V1D_LAUNCH_SCRIPT:-${ROOT}/scripts/launch-v1d-terminal.sh}"
if [[ ! -x "$LAUNCH" ]]; then
  LAUNCH="${ROOT}/scripts/launch-v1d-gui.sh"
fi
PARALLEL_LOG="${V1D_RELOAD_LOG_TERMINAL:-1}"

mkdir -p "$STATE_DIR"
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

_fix_session_env() {
  if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]] && [[ -n "${XDG_RUNTIME_DIR:-}" ]] && [[ -S "${XDG_RUNTIME_DIR}/bus" ]]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"
  fi
}
_fix_session_env

_write_wrapper() {
  local path="$1"
  shift
  {
    echo '#!/usr/bin/env bash'
    echo 'set -euo pipefail'
    printf 'export V1D_ROOT=%q\n' "${V1D_ROOT:-$ROOT}"
    printf 'export V1D_LAUNCH_SCRIPT=%q\n' "$LAUNCH"
    [[ -n "${V1D_CLIP:-}" ]] && printf 'export V1D_CLIP=%q\n' "$V1D_CLIP"
    [[ -n "${DISPLAY:-}" ]] && printf 'export DISPLAY=%q\n' "$DISPLAY"
    [[ -n "${WAYLAND_DISPLAY:-}" ]] && printf 'export WAYLAND_DISPLAY=%q\n' "$WAYLAND_DISPLAY"
    [[ -n "${XAUTHORITY:-}" ]] && printf 'export XAUTHORITY=%q\n' "$XAUTHORITY"
    [[ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]] && printf 'export DBUS_SESSION_BUS_ADDRESS=%q\n' "$DBUS_SESSION_BUS_ADDRESS"
    [[ -n "${XDG_RUNTIME_DIR:-}" ]] && printf 'export XDG_RUNTIME_DIR=%q\n' "$XDG_RUNTIME_DIR"
    printf 'cd %q\n' "$ROOT"
    "$@"
  } >"$path"
  chmod +x "$path"
}

KIT_WRAPPER="${STATE_DIR}/reload-launch.sh"
_write_wrapper "$KIT_WRAPPER" printf 'exec bash %q\n' "$LAUNCH"

TAIL_WRAPPER="${STATE_DIR}/reload-tail-log.sh"
_write_wrapper "$TAIL_WRAPPER" \
  printf 'touch %q\n' "$LOG" \
  echo 'echo "=== v1d live log (tail -f) ==="' \
  printf 'echo Log file: %q\n' "$LOG" \
  echo 'echo' \
  printf 'exec tail -n 120 -f %q\n' "$LOG"

_open_terminal() {
  local title="$1"
  local cmd_path="$2"

  if [[ -x /usr/bin/x-terminal-emulator ]]; then
    nohup /usr/bin/x-terminal-emulator -T "$title" -e "$cmd_path" </dev/null >/dev/null 2>&1 &
    echo "[$(date -Is)] terminal ($title): x-terminal-emulator" >>"$RELOAD_LOG"
    return 0
  fi
  if command -v gnome-terminal >/dev/null 2>&1; then
    if nohup setsid gnome-terminal --title="$title" --wait=false --hold -- "$cmd_path" </dev/null >/dev/null 2>&1 & then
      echo "[$(date -Is)] terminal ($title): gnome-terminal" >>"$RELOAD_LOG"
      return 0
    fi
  fi
  if command -v konsole >/dev/null 2>&1; then
    nohup konsole --separate --hold -p "tabtitle=$title" -e "$cmd_path" </dev/null >/dev/null 2>&1 &
    echo "[$(date -Is)] terminal ($title): konsole" >>"$RELOAD_LOG"
    return 0
  fi
  if command -v xfce4-terminal >/dev/null 2>&1; then
    nohup xfce4-terminal --title="$title" --hold -e "$cmd_path" </dev/null >/dev/null 2>&1 &
    echo "[$(date -Is)] terminal ($title): xfce4-terminal" >>"$RELOAD_LOG"
    return 0
  fi
  if command -v xterm >/dev/null 2>&1; then
    nohup xterm -T "$title" -hold -e "$cmd_path" </dev/null >/dev/null 2>&1 &
    echo "[$(date -Is)] terminal ($title): xterm" >>"$RELOAD_LOG"
    return 0
  fi
  return 1
}

kit_term_ok=0
log_term_ok=0

if [[ "$PARALLEL_LOG" != "0" ]]; then
  if _open_terminal "v1d logs" "$TAIL_WRAPPER"; then
    log_term_ok=1
  fi
fi

if _open_terminal "v1d" "$KIT_WRAPPER"; then
  kit_term_ok=1
fi

if [[ "$kit_term_ok" -eq 1 ]]; then
  echo "[$(date -Is)] Reload OK (kit terminal, log_terminal=${log_term_ok})" >>"$RELOAD_LOG"
  exit 0
fi

echo "[$(date -Is)] Reload: no Kit terminal; detached start" >>"$RELOAD_LOG"
nohup "$KIT_WRAPPER" >>"$RELOAD_LOG" 2>&1 &
disown || true

if [[ "$log_term_ok" -eq 0 ]] && [[ "$PARALLEL_LOG" != "0" ]]; then
  _open_terminal "v1d logs" "$TAIL_WRAPPER" || true
fi
exit 0
