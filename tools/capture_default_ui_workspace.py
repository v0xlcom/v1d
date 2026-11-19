#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One-shot: run inside Kit after v1d + Console are up; writes default workspace JSON into the extension."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import omni.ui as ui

OUT = Path(__file__).resolve().parents[1] / "source/extensions/v1d.pv/data/ui_workspace_default.json"


def main() -> int:
    scrub = ui.Workspace.get_window("v1d Scrub")
    console = ui.Workspace.get_window("Console")
    if not scrub or not console:
        print("capture: need windows 'v1d Scrub' and 'Console'", file=sys.stderr)
        return 1
    console.dock_in(scrub, ui.DockPosition.BOTTOM, 0.32)
    dump = ui.Workspace.dump_workspace()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dump, indent=2) + "\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
