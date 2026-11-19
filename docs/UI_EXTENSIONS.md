# v1d UI extensions

## Stack

| Extension | Role |
|-----------|------|
| **`v1d.cor`** | GPU scrub via **`v1d.ngn`**, `ScrubSession`, `tools/v1d serve`, shared **`v1d.kit`** window-menu helpers |
| **`v1d.pv`** | Preview, workspace layout, Reload, S2/C10 dev modes — depends on **core** |
| **`v1d.tl`** | Timeline (Lens: `omni.ui` bands for the cyan bar, ruler, clock, and detail grid; scene lines only for the trapezoid edges). Playhead is on the full strip, not inside the cyan bar. Depends on **core** + **`omni.ui.scene`** |
| **`v1d.ups`** | Upscaler (six engines, wipe compare) — **v1d → Window → Upscaler**; depends on **core** only |
| **`v1d.rnd`** | Render composition to MP4 — **File → Render…** / **v1d → Window → Render**; depends on **core** |

New feature extensions should depend on **`v1d.cor`** (and add `omni.ui` locally if they need windows).

Engine settings: `/exts/v1d.cor/*` (`clip`, `cuda_device`, …). Shell UI: `/exts/v1d.pv/ui/*`. **File** menu: New/Open/Save `.v1d`, Add Video, Open Video, Render…, Quit (`v1d.kit.project_hooks` + `v1d.tl` handlers).

## Timeline wheel zoom

This is the wheel contract. **Zoom − / Zoom +** stay `zoom(0.5)` / `zoom(2)`. The wheel does not use those factors. Archived plans that say the wheel calls `zoom(2)` or `zoom(0.5)`, or that the wheel stays unbound, are out of date.

- **100%** is the whole sequence in the window. Each wheel notch steps **5 percentage points**: 100, 95, 90, … and back.
- **Closest zoom** is one second of frames (`px_max = width / fps`). On GOP 30 (600 frames, 30 fps) that floor is **5%**. A shorter clip stops higher. Do not collapse the ladder to one step.
- The frame under the pointer stays at the **horizontal center** of the detail strip (`set_zoom_percent(..., center=True)`). The playhead index does not change.
- `mouse_wheel_fn` is `(x, y, modifier)` and has **no scroll delta**. Do not treat `modifier` as the direction.
- Read `SCROLL_UP` and `SCROLL_DOWN`. One callback is one notch. Those readings often **repeat** (`1` and `0`) instead of accumulating. A repeated level in the same direction is still a new step. If the counters changed, use that delta. If both are 0 and neither changed, do nothing.
- Code: `wheel_zoom_direction` and `next_wheel_zoom_percent` in `source/extensions/v1d.tl/python/v1d/tl/view.py`. Tests: `TestWheelZoomPercent` in `source/extensions/v1d.cor/python/tests/test_timeline_view.py`. Kit check: [GUI_TEST_PLAN.md](GUI_TEST_PLAN.md) §7.7.

## Window menu

**v1d → Window → &lt;title&gt;** — use `v1d.kit.window_menu` (`MenuHelperExtension` + workspace). The main menu bar (`v1d.pv.ui.menu_bar`) has **File** (Open Video, Quit), **Power** (Performance / Balanced / Powersave via `powerprofilesctl`), and **Reload**. Quit saves the workspace and uses Kit `post_quit(0)` with `fastShutdown` left false so extension shutdown still runs. Menu checks and radios use 6 px squares (`v1d.kit.square_menu`): cyan when on, console-log grey (`#1F2124`) when off, playhead magenta on hover (including the selected item).
