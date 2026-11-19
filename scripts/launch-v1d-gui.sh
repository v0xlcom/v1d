#!/usr/bin/env bash
# Alias for dock/menu entries that still point at launch-v1d-gui.sh.
exec "$(dirname "${BASH_SOURCE[0]}")/launch-v1d-terminal.sh" "$@"
